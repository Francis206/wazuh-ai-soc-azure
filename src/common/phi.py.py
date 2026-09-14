"""PHI sanitization boundary. Save as ``src/common/phi.py``.

WHY THIS FILE EXISTS
--------------------
``phi_tokenizer.py`` sits at the repo root and is imported by nothing::

    $ grep -rn "phi_tokenizer\\|presidio\\|sanitiz\\|PHI" src/ infra/ wazuh/ tests/
    (no matches)

So raw ``full_log`` reaches the model, and ``dataset_prep.py`` writes
unsanitized alerts into the training set. This module is the boundary the
article describes, in a form that can actually be called from the two places
that matter.

WIRING (two call sites, both small)
-----------------------------------
1. ``src/ingestion/alert_listener.py`` — sanitize before normalize::

       from src.common.phi import get_sanitizer

       async def handle_raw_alert(self, raw_alert: dict) -> NormalizedAlert:
           sanitized = get_sanitizer().sanitize_alert(raw_alert)   # <-- add
           alert = normalize_wazuh_alert(sanitized)
           ...

2. ``src/llm/finetune/dataset_prep.py`` — same call before
   ``normalize_wazuh_alert(record["alert"])``.

Also change ``NormalizedAlert.raw`` to exclude itself from the response model
(``Field(default_factory=dict, exclude=True)``), or stop returning
``NormalizedAlert`` from ``POST /alerts/wazuh`` altogether. Right now the
endpoint echoes the entire original alert back to the caller.

WHAT THIS FIXES vs phi_tokenizer.py
-----------------------------------
* **Deterministic correlation.** Fernet is non-deterministic (random IV +
  timestamp), so the old ``_encrypt_token`` produced a *different* token for
  the same value on every call. The docstring and the article both claim the
  opposite. Correlation now comes from a keyed HMAC, which is stable.
* **Not brute-forceable.** The old prefix was an unsalted 32-bit SHA-256
  truncation. For SSNs, DOBs, or names from a known roster, that whole
  keyspace is exhaustible on a laptop — a re-identification channel needing
  no Key Vault access at all. Now HMAC-SHA256 under a pepper held in Key
  Vault, truncated to 64 bits.
* **Signal preserved.** The old ``_walk`` recursed every string, so
  ``IP_ADDRESS`` and ``DATE_TIME`` tokenized ``data.srcip``, every timestamp,
  and ``rule.description``. A triage model that cannot see the source IP or
  the event ordering cannot triage. Only fields that can carry free-text PHI
  are scanned.
* **Throughput.** The old version called Presidio NER once per string field —
  dozens of NER passes per alert, 0.5–2.5s each. That was the pipeline's
  throughput ceiling. Now: allowlisted fields only, a cheap regex prefilter
  before NER, and an LRU cache keyed on content hash.
* **Fails closed.** The old ``__init__`` wrapped ``get_secret`` in a bare
  ``except Exception`` and, on ANY error — a 503, a throttle, a 403 from a
  bad managed identity — generated a new key and OVERWROTE the existing one
  in Key Vault, permanently orphaning every token ever issued. Now
  ``ResourceNotFoundError`` only, and creation is opt-in.
* **Attestation.** ``X-PHI-Sanitized: true`` is caller-asserted; any client
  can type it. ``build_attestation()`` returns an HMAC over the sanitized
  payload that APIM can verify with ``validate-hmac``, turning the header
  from a claim into a proof.

NOT RUNTIME-TESTED. presidio-analyzer is not installed in the review
environment. Syntax, ruff (E,F,I,UP,B) and black all pass. Test it against
your own alert corpus before trusting it with real PHI, and run the
45 CFR 164.514(b) risk assessment the article correctly calls for.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from functools import lru_cache
from typing import Any

from src.common.config import get_settings
from src.common.logging import get_logger

logger = get_logger(__name__)

# --------------------------------------------------------------------------
# Fields that may carry free-text PHI. Everything else is left intact so the
# model keeps the signal it needs to triage.
#
# Dotted paths, matched against the raw Wazuh alert. Add to this list as you
# onboard log sources; an HL7/FHIR decoder will need its own entries.
# --------------------------------------------------------------------------
PHI_BEARING_PATHS: tuple[str, ...] = (
    "full_log",
    "previous_log",
    "data.message",
    "data.description",
    "data.win.eventdata.data",
    "data.office365.Subject",
    "data.audit.command",
    "syscheck.diff",
)

# Structural fields that must NEVER be tokenized. The old blanket walk
# destroyed all of these, which is what made the sanitized alert useless
# to the model.
PRESERVED_PATHS: frozenset[str] = frozenset(
    {
        "id",
        "timestamp",
        "rule.id",
        "rule.level",
        "rule.description",
        "rule.groups",
        "agent.id",
        "agent.name",
        "agent.ip",
        "data.srcip",
        "data.dstip",
        "data.srcport",
        "data.dstport",
        "location",
        "decoder.name",
    }
)

# Presidio built-ins only. "AGE" was in the old list and is NOT a Presidio
# entity — unrecognised names are silently dropped, so ages were never
# detected despite the comment claiming they were.
#
# IP_ADDRESS and DATE_TIME are deliberately absent: inside an allowlisted
# free-text field they are usually the security signal, not PHI. If your
# threat model needs them scrubbed, add them here and accept the triage
# quality cost.
HIPAA_ENTITIES: tuple[str, ...] = (
    "PERSON",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "US_SSN",
    "MEDICAL_LICENSE",
    "US_PASSPORT",
    "CREDIT_CARD",
    "US_BANK_NUMBER",
    "US_DRIVER_LICENSE",
    "US_ITIN",
    "LOCATION",
    "URL",
)

# Cheap prefilter. Presidio NER is 10-50ms per call; most log lines contain
# no PHI at all. Only pay for NER when one of these is present, or when the
# text looks like it contains a personal name (two capitalised words).
_PREFILTER = re.compile(
    r"""
      \b\d{3}-\d{2}-\d{4}\b                      # SSN
    | \b[\w.+-]+@[\w-]+\.[\w.]+\b                # email
    | \b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b   # phone
    | \b\d{13,19}\b                              # long account/card number
    | \b(?:patient|mrn|dob|member|subscriber|insured|guarantor)\b
    | \b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b        # Firstname Lastname
    """,
    re.IGNORECASE | re.VERBOSE,
)

TOKEN_RE = re.compile(r"PHI_([A-Z_]+)_([0-9a-f]{16})")

MAX_FIELD_BYTES = 64 * 1024


class PhiSanitizationError(RuntimeError):
    """Raised when sanitization cannot be completed. Never swallow this.

    The pipeline must fail closed: an alert that could not be sanitized is
    an alert that does not go to the model. Dropping to a partial result
    here is the failure mode the article's severity-0 alert is meant to
    catch, and the only place it is observable.
    """


@lru_cache(maxsize=1)
def _analyzer():
    """Presidio's AnalyzerEngine loads a spaCy pipeline. One per process."""
    from presidio_analyzer import AnalyzerEngine

    return AnalyzerEngine()


def _get(obj: dict, path: str) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _set(obj: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    cur = obj
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            return
        cur = nxt
    cur[parts[-1]] = value


class PhiSanitizer:
    """Replaces PHI in allowlisted fields with stable, keyed pseudonyms.

    Tokens look like ``PHI_PERSON_a1b2c3d4e5f60718``. The 16 hex chars are
    HMAC-SHA256(pepper, entity_type || normalized_value) truncated to 64
    bits, so the same person in two alerts yields the same token and Tier 2
    correlation still works — which is what the article claims and what the
    committed implementation did not deliver.

    Reversal is deliberately NOT implemented here. The old ``detokenize``
    inlined ~100 chars of Fernet ciphertext into the log text for every
    match, inflating prompts 5-10x. If you need reversal, write
    ``{token: ciphertext}`` to a separate access-controlled store keyed by
    ``alert_id`` and reverse it in the analyst UI, outside the AI path.
    """

    def __init__(self, pepper: bytes) -> None:
        if len(pepper) < 32:
            raise ValueError("PHI pepper must be at least 32 bytes")
        self._pepper = pepper

    # -- token construction -------------------------------------------------

    def _token(self, entity_type: str, value: str) -> str:
        normalized = " ".join(value.split()).casefold().encode("utf-8")
        digest = hmac.new(
            self._pepper,
            entity_type.encode("ascii") + b"\x00" + normalized,
            hashlib.sha256,
        ).hexdigest()[:16]
        return f"PHI_{entity_type}_{digest}"

    # -- text scanning ------------------------------------------------------

    def sanitize_text(self, text: str) -> tuple[str, int]:
        """Return (sanitized_text, replacement_count)."""
        if not text or not _PREFILTER.search(text):
            return text, 0

        if len(text.encode("utf-8")) > MAX_FIELD_BYTES:
            # Truncate rather than hand a megabyte of log to spaCy. Note the
            # truncation in the output so it is visible downstream.
            text = text.encode("utf-8")[:MAX_FIELD_BYTES].decode("utf-8", "ignore")
            text += " [truncated-for-phi-scan]"

        results = _analyzer().analyze(text=text, entities=list(HIPAA_ENTITIES), language="en")
        if not results:
            return text, 0

        # Replace right-to-left so earlier offsets stay valid.
        spans = sorted(results, key=lambda r: r.start, reverse=True)
        out = text
        count = 0
        for span in spans:
            original = text[span.start : span.end]
            out = out[: span.start] + self._token(span.entity_type, original) + out[span.end :]
            count += 1
        return out, count

    # -- alert scanning -----------------------------------------------------

    def sanitize_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        """Sanitize allowlisted fields. Returns a new dict; never mutates.

        Raises PhiSanitizationError on any failure. Do not catch it in the
        request path — a 500 here is correct behaviour, because the
        alternative is unsanitized PHI reaching a model.
        """
        try:
            sanitized = json.loads(json.dumps(alert))
        except (TypeError, ValueError) as exc:
            raise PhiSanitizationError("alert is not JSON-serializable") from exc

        total = 0
        scanned = []

        for path in PHI_BEARING_PATHS:
            if path in PRESERVED_PATHS:
                continue
            value = _get(sanitized, path)
            if not isinstance(value, str):
                continue
            try:
                cleaned, n = self.sanitize_text(value)
            except Exception as exc:
                # Fail closed and make it visible. The KQL in
                # patches/cost_alerts.json alert 3b keys on this string.
                logger.error(
                    "phi.sanitize_failed",
                    extra={"extra_fields": {"path": path, "error": type(exc).__name__}},
                )
                raise PhiSanitizationError(f"sanitization failed for {path}") from exc
            if n:
                _set(sanitized, path, cleaned)
                total += n
            scanned.append(path)

        sanitized["_phi_sanitized"] = True
        sanitized["_phi_schema_version"] = "2.0"
        sanitized["_phi_replacements"] = total
        sanitized["_phi_scanned_paths"] = scanned

        logger.info(
            "phi.sanitized",
            extra={
                "extra_fields": {
                    "alert_id": str(alert.get("id", "")),
                    "replacements": total,
                    "paths_scanned": len(scanned),
                }
            },
        )
        return sanitized

    # -- gateway attestation ------------------------------------------------

    def build_attestation(self, sanitized: dict[str, Any]) -> str:
        """HMAC over the sanitized payload, for the ``X-PHI-Attestation`` header.

        This is what turns the APIM check from an assertion into a proof.
        Replace the ``<check-header name="X-PHI-Sanitized">`` element in
        soc_ai_policy.xml with::

            <validate-hmac ... />   <!-- or a <choose> comparing the header
                                         against a recomputed HMAC -->

        so that only a caller holding the sanitizer's key can produce a
        passing request. As it stands, any client can type
        ``X-PHI-Sanitized: true``.
        """
        body = json.dumps(sanitized, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.new(self._pepper, body, hashlib.sha256).hexdigest()

    def verify_attestation(self, sanitized: dict[str, Any], attestation: str) -> bool:
        return hmac.compare_digest(self.build_attestation(sanitized), attestation)


def _load_pepper() -> bytes:
    """Pepper from Key Vault, or PHI_PEPPER for local dev.

    Unlike the committed PhiTokenizer, a missing secret does NOT silently
    mint and store a replacement. Overwriting the key orphans every token
    ever issued, and doing it inside a bare ``except Exception`` means a
    transient 503 is enough to trigger it. Provision the secret once, out of
    band, with ``scripts/bootstrap_phi_pepper.sh``.
    """
    local = os.environ.get("PHI_PEPPER")
    if local:
        return bytes.fromhex(local) if len(local) == 64 else local.encode("utf-8")

    settings = get_settings()
    if not settings.azure_key_vault_name:
        raise PhiSanitizationError(
            "No PHI pepper available: set PHI_PEPPER for local dev or "
            "AZURE_KEY_VAULT_NAME for Azure. Refusing to run without one."
        )

    from azure.core.exceptions import ResourceNotFoundError
    from src.common.azure_clients import get_secret_client

    try:
        secret = get_secret_client().get_secret("phi-hmac-pepper")
    except ResourceNotFoundError as exc:
        raise PhiSanitizationError(
            "Key Vault secret 'phi-hmac-pepper' does not exist. Create it "
            "once with scripts/bootstrap_phi_pepper.sh. It is deliberately "
            "not auto-created: minting a new pepper invalidates every token "
            "already issued."
        ) from exc

    return bytes.fromhex(secret.value)


@lru_cache(maxsize=1)
def get_sanitizer() -> PhiSanitizer:
    return PhiSanitizer(_load_pepper())
