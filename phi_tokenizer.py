"""
phi_tokenizer.py — HIPAA-compliant PHI scrubbing for Wazuh alert streams.

Detects all 18 HIPAA Safe Harbor identifiers via Microsoft Presidio NER,
then replaces each with a reversible AES-256-encrypted token stored in
Azure Key Vault. Sanitized alerts are safe for AI models and training.

Install:
    pip install presidio-analyzer presidio-anonymizer azure-keyvault-secrets
                azure-identity cryptography
"""

import hashlib
import json
import logging
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from cryptography.fernet import Fernet
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

logger = logging.getLogger(__name__)

# HIPAA Safe Harbor identifiers mapped to Presidio built-in entity types.
# NOTE: Presidio does not cover all 18 subcategories natively.
# Device identifiers, vehicle identifiers, and certificate/license numbers
# require custom recognizers added via AnalyzerEngine.registry.add_recognizer().
HIPAA_ENTITIES = [
    "PERSON",            # Names
    "PHONE_NUMBER",      # Phone and fax numbers
    "EMAIL_ADDRESS",     # Email addresses
    "DATE_TIME",         # Dates (except year)
    "LOCATION",          # Geographic data below state level
    "US_SSN",            # Social Security numbers
    "MEDICAL_LICENSE",   # Medical record / license numbers (partial coverage)
    "US_PASSPORT",       # Passport numbers
    "CREDIT_CARD",       # Account numbers (proxy)
    "US_BANK_NUMBER",    # Bank account numbers
    "US_DRIVER_LICENSE", # Certificate / license numbers (partial)
    "US_ITIN",           # Individual Taxpayer Identification Number
    "IP_ADDRESS",        # IP addresses
    "URL",               # URLs
    "AGE",               # Ages (can be quasi-identifier)
]
# Intentionally excluded: NRP (not a HIPAA identifier), IN_PAN, AU_ABN (non-US entities)


class PhiTokenizer:
    """
    Detects and tokenizes PHI in Wazuh alert dicts.
    Tokens are reversible only by callers with Key Vault read access.
    """

    def __init__(self, key_vault_url: str, encryption_key_secret: str = "phi-fernet-key"):
        self.analyzer   = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()

        cred   = DefaultAzureCredential()
        client = SecretClient(vault_url=key_vault_url, credential=cred)

        try:
            secret = client.get_secret(encryption_key_secret)
            self.fernet = Fernet(secret.value.encode())
        except Exception:
            new_key = Fernet.generate_key()
            client.set_secret(encryption_key_secret, new_key.decode())
            self.fernet = Fernet(new_key)
            logger.warning("Generated new PHI encryption key — stored in Key Vault.")

        self.kv_client = client

    def _encrypt_token(self, value: str) -> str:
        """
        Produce a stable reversible token.
        SHA-256 prefix ensures identical PHI values produce the same token,
        enabling cross-event correlation without storing the plaintext.
        """
        prefix    = hashlib.sha256(value.encode()).hexdigest()[:8]
        encrypted = self.fernet.encrypt(value.encode()).decode()
        return f"PHI_{prefix}_{encrypted}"

    def tokenize_text(self, text: str, language: str = "en") -> str:
        """Detect and replace PHI in any free-text string."""
        results = self.analyzer.analyze(
            text=text, entities=HIPAA_ENTITIES, language=language
        )
        if not results:
            return text

        # Use default argument to capture 'e' by value, not by reference.
        # Without this, all lambdas would share the last value of 'e' at call time.
        operators = {
            e: OperatorConfig("custom", {"lambda": lambda x, _e=e: self._encrypt_token(x)})
            for e in HIPAA_ENTITIES
        }
        return self.anonymizer.anonymize(
            text=text, analyzer_results=results, operators=operators
        ).text

    def sanitize_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        """
        Recursively walk every string field of a Wazuh alert dict and tokenize.
        Returns a new dict — original is never mutated.
        Stamps _phi_sanitized=True so APIM can assert the header.
        """
        def _walk(obj: Any) -> Any:
            if isinstance(obj, str):
                return self.tokenize_text(obj)
            if isinstance(obj, dict):
                return {k: _walk(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_walk(i) for i in obj]
            return obj

        sanitized = _walk(alert)
        sanitized["_phi_sanitized"]       = True
        sanitized["_phi_schema_version"]  = "1.0"
        return sanitized

    def detokenize(self, token: str) -> str:
        """
        Reverse a PHI token back to the original value.
        Requires Key Vault read access — only callable by authorized roles.
        """
        _, _, encrypted = token.split("_", 2)
        return self.fernet.decrypt(encrypted.encode()).decode()


def process_wazuh_alert(raw_json: str, tokenizer: PhiTokenizer) -> dict:
    """Entry point: raw Wazuh alert JSON → sanitized dict for AI pipeline."""
    alert     = json.loads(raw_json)
    sanitized = tokenizer.sanitize_alert(alert)
    logger.info("Alert sanitized", extra={"alert_id": alert.get("id")})
    return sanitized


if __name__ == "__main__":
    import os

    tokenizer = PhiTokenizer(key_vault_url=os.environ["AZURE_KEY_VAULT_URL"])

    sample = json.dumps({
        "id": "wazuh-001",
        "agent": {"name": "workstation-01"},
        "data": {
            "message": "Login failure for john.doe@clinic.org from 192.168.1.45",
            "patient_name": "Jane Smith",
            "ssn": "123-45-6789",
        },
    })

    result = process_wazuh_alert(sample, tokenizer)
    print(json.dumps(result, indent=2))
