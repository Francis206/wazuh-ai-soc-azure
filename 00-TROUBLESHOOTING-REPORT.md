# wazuh-ai-soc-azure — Troubleshooting Report

**Repo:** `github.com/Francis206/wazuh-ai-soc-azure` @ `dd7bae1` (4 commits, main)
**Companion article:** *Open-Source AI-Augmented SOC on Azure* (Medium, 25 Apr 2026)
**Reviewed:** 13 Sep 2026 — static analysis, HCL/XML/JSON parsing, dependency install, full test run.
**Nothing in this report was committed.** All fixes are in `patches/` for you to apply yourself.

---

## Verdict

The repo is two codebases glued together and neither half runs end to end.

* **Half A** (`src/`, `tests/`, `infra/`, `docker/`, `wazuh/`, `docs/`) is a clean, well-commented FastAPI + Terraform-module project. `ruff` and `black` pass on it. All 12 tests pass.
* **Half B** (`main.tf`, `phi_tokenizer.py`, `mlops_pipeline.py`, `soc_ai_policy.xml`, `cost_alerts.json` at the repo root) is the article's artifact set. It is not linted, not tested, not imported by anything, and describes a *different architecture* (AKS + APIM + Ollama Container Apps) than Half A (single VM + docker-compose + transformers).

The README is literally both halves with the merge conflict markers left in.

Empirical results:

| Check | Result |
|---|---|
| `pytest tests` | **12 passed** |
| `ruff check src tests` | **clean** |
| `black --check src tests` | **clean** |
| `ruff check phi_tokenizer.py mlops_pipeline.py` | **1 error (I001)** |
| `black --check phi_tokenizer.py mlops_pipeline.py` | **2 files would reformat** |
| HCL parse `main.tf` | **FAIL — line 102** |
| HCL parse `infra/**/*.tf` (20 files) | **all OK** |
| XML parse `wazuh/decoders/local_ml_decoders.xml` | **FAIL — junk after document element** |
| `curl` the URL cloud-init clones | **404** |

The single most falsifiable sentence in the article — *"The complete code is production-ready and deployable using a simple Terraform apply command"* — is false: `main.tf` does not parse.

---

## P0 — Blocks deployment or silently defeats the stated purpose

### P0-1 · README.md is a committed merge conflict

`README.md` line 1 is `<<<<<<< HEAD`, line ~60 is `=======`, and the last line is
`>>>>>>> 887ba77effca7e9ef0020a4c8f2a6b687fa245d2`. Both versions of the README are in the file. GitHub renders the second half, so the landing page advertises the root-level `terraform/`, `python/`, `apim/`, `finops/` layout — which does not exist; those files are flat at the root.

Two further factual errors in the surviving half:
* `> Published on InfoQ DevOps/Cloud · April 2026` — the article is on Medium.
* The file table points to `terraform/main.tf`, `python/phi_tokenizer.py`, `apim/soc_ai_policy.xml`, `finops/cost_alerts.json`. None of those paths exist.

**Fix:** `patches/README.md`

---

### P0-2 · `main.tf` is not valid HCL — three parse errors

HCL does not allow comma-separated arguments inside a **block body**. (It *is* allowed inside object *expressions*, which is why `tags = { a = 1, b = 2 }` on line 20 is fine and these are not.)

```
main.tf:102   env { name = "OLLAMA_MODELS", value = "/mnt/models" }
main.tf:110   traffic_weight { percentage = 100, latest_revision = true }
main.tf:198   output "aks_kube_config" { value = ...kube_config_raw, sensitive = true }
```

Confirmed by parser: `Unexpected token Token('COMMA', ',') at line 102, column 35`. `terraform init` never gets as far as the provider download. The README's advertised two-line deploy is dead on the first command.

**Fix:** `patches/main.tf`

---

### P0-3 · The PHI boundary does not exist in the running pipeline

This is the most serious finding, because PHI enforcement is the article's central claim.

```
$ grep -rn "phi_tokenizer\|presidio\|sanitiz\|PHI" src/ infra/ wazuh/ tests/ docker/ docs/
(no matches)
```

`phi_tokenizer.py` sits at the repo root and is imported by **nothing**. The live path is:

```
Wazuh alert → ml_pipeline_integration.py → POST /alerts/wazuh
            → normalize_wazuh_alert()  (keeps full_log AND raw verbatim)
            → build_triage_prompt()    (interpolates full_log into the prompt)
            → LLM
```

Raw `full_log` reaches the model unmodified. `dataset_prep.py` does the same for training data, so *"All training data is PHI-sanitized before reaching Azure ML"* is also unsupported.

Two compounding problems:
* `NormalizedAlert.raw` stores the entire original alert, and `NormalizedAlert` is the `response_model` of `POST /alerts/wazuh` — so the API echoes the full unsanitized alert back to the caller.
* The APIM `X-PHI-Sanitized: true` header is **self-asserted by the caller**. Any client can set it. It is a checkbox, not a control.

**Fix:** `patches/src_common_phi.py` (a real sanitization boundary with an HMAC attestation the gateway can verify) plus the wiring diff in the same file's header comment.

---

### P0-4 · The entire Wazuh rule chain is dead

```xml
<rule id="100010" level="10">
  <if_sid>100000</if_sid>
  <field name="ml_pipeline_eligible">true</field>   <!-- nothing ever sets this -->
```

No decoder in `wazuh/decoders/`, no agent config, and nothing in `src/` ever produces an `ml_pipeline_eligible` field. So 100010 never fires. 100020 is `<if_matched_sid>100010</if_matched_sid>` and 100030 is `<if_matched_sid>100020</if_matched_sid>`, so the whole chain is dead.

Consequence: no alert ever carries `ml_pipeline_tier2` or `ml_pipeline_tier3`, so `tier_from_wazuh_groups()` always returns `TIER_1`, so `SocOrchestrator` never routes to Tier 2 or Tier 3 by rule group. The Tier 1/2/3 routing that the article's architecture rests on is inert.

Secondary: rule 100030 uses `<if_matched_sid>` with no `frequency`/`timeframe`, which is not a valid composite correlation rule.

**Fix:** `patches/local_ml_rules.xml`

---

### P0-5 · Rules, decoders, and the integration are never loaded by Wazuh

```yaml
- ./wazuh/rules:/var/ossec/etc/rules/custom:ro
- ./wazuh/decoders:/var/ossec/etc/decoders/custom:ro
- ./wazuh/integrations/ml_pipeline_integration.py:/var/ossec/integrations/custom-ml-pipeline:ro
```

* Wazuh reads `etc/rules/*.xml` and `etc/decoders/*.xml`. It does **not** recurse into a `custom/` subdirectory unless `ossec.conf` declares an extra `<rule_dir>`. It does not.
* A custom integration script does nothing until an `<integration>` block is added to `ossec.conf`. There is no `ossec.conf` in the repo and no compose mount for one.
* The script is mounted `:ro` from the host, so it will not have the `750 root:wazuh` ownership Wazuh requires to execute it.

So even with P0-4 fixed, nothing reaches the API.

**Fix:** `patches/docker-compose.yml` (correct mount paths) + `patches/ossec-conf-snippet.xml` (the `<integration>` block).

---

### P0-6 · cloud-init clones a repository that does not exist

```hcl
# infra/modules/wazuh_compute/variables.tf
variable "repo_url" {
  default = "https://github.com/francis206/wazuh_azure_ml_mml.git"
}
```

```
$ curl -o /dev/null -w "%{http_code}" https://api.github.com/repos/francis206/wazuh_azure_ml_mml
404
```

The Azure Wazuh VM boots, installs Docker, fails the `git clone`, and sits there empty. `runcmd` is not `set -e`, so the VM reports healthy. Terraform reports success. Nothing is running.

**Fix:** point the default at `https://github.com/Francis206/wazuh-ai-soc-azure.git` — see `patches/wazuh_compute-variables.tf`.

---

### P0-7 · `.github/workflows/` does not exist but is referenced six times

There is no `.github` directory. It is cited in:

```
README.md:22                          | CI/CD | ... | `.github/workflows/` |
docs/architecture.md:90               ### 6. CI/CD (`.github/workflows/`)
docs/deployment.md §2                 terraform.yml and ml-training.yml ...
src/llm/finetune/train.py:4           submitted ... by .github/workflows/ml-training.yml
src/llm/finetune/config.yaml:3        also read by .github/workflows/ml-training.yml
src/llm/evaluation/evaluate.py:6      Invoked ... from .github/workflows/ml-training.yml
tests/integration/test_alerts_endpoint.py:4   covered by ... ml-training.yml
```

The article describes this in the most detail of any section — five stages, OIDC federation, Trivy, load test at 1,000 alerts/min, a named-approver gate, blue/green with auto-rollback. None of it is in the repo.

**Fix:** `patches/github-workflows/ci.yml` — a working Stage-2 quality gate (lint, test, XML/JSON/HCL validation, Trivy, `terraform validate`) that runs with no cloud credentials, so it is safe to merge today. It is the honest subset; the deploy stages need real secrets.

---

### P0-8 · `cost_alerts.json` cannot deploy

Three independent blockers:

1. **`scopes` is missing on all four rules.** `microsoft.insights/scheduledQueryRules` API `2023-03-15` requires a `scopes` array naming the Log Analytics workspace or resources to query. ARM validation fails before anything is created.
2. **The action group is never created.** All four rules reference `resourceId('microsoft.insights/actionGroups', concat('ag-soc-', parameters('env')))`. No `actionGroups` resource exists in this template, in `main.tf`, or in `infra/`.
3. **`actionGroupEmail` is declared and never used.** The template takes an email address and drops it.

Also missing: `metricMeasureColumn` on the two rules whose queries `summarize` into a named column (`Total`, `NodeCount`) while declaring a non-`Count` aggregation.

**Fix:** `patches/cost_alerts.json`

---

### P0-9 · `mlops_pipeline.py` points at three directories that do not exist

```python
code="./components/data_prep"    # not in repo
code="./components/finetune"     # not in repo
code="./components/evaluate"     # not in repo
```

`ml_client.jobs.create_or_update()` fails at snapshot upload. Additionally `register()` — the function that implements step 4 of the docstring's own four-step pipeline — is defined and never called; `__main__` only submits and prints.

This file also duplicates `src/llm/finetune/train.py` and `src/llm/evaluation/evaluate.py`, giving you three competing training entry points (`mlops_pipeline.py`, `scripts/submit_azureml_finetune_job.py`, `make train`).

**Recommendation:** delete `mlops_pipeline.py` and keep `scripts/submit_azureml_finetune_job.py` as the single Azure ML entry point, after fixing P1-14 below. Two implementations of the same pipeline is the root cause of most of this report.

---

### P0-10 · The fine-tuning job crashes on the first batch

```python
def tokenize_dataset(dataset, tokenizer, prompt_field, completion_field):
    def _tokenize(example):
        text = example[prompt_field] + "\n" + example[completion_field] + tokenizer.eos_token
        return tokenizer(text, truncation=True, max_length=2048)
    return dataset.map(_tokenize, remove_columns=dataset.column_names)

trainer = Trainer(model=model, args=training_args,
                  train_dataset=train_dataset, eval_dataset=eval_dataset,
                  tokenizer=tokenizer)          # no data_collator
```

Two defects:
* **No padding.** With no `data_collator`, `Trainer` falls back to `default_data_collator`, which stacks tensors without padding. Variable-length sequences → `RuntimeError` on the first batch of size 4.
* **No `labels`.** Even padded, causal LM loss needs a `labels` column. `DataCollatorForLanguageModeling(mlm=False)` creates it.

A quality issue on top: loss is computed over the prompt tokens as well as the completion. For instruction tuning you want the prompt masked to `-100` so the model learns to *produce* the verdict, not to reproduce the alert.

Also `tokenizer=` is deprecated in transformers 4.44 (pinned) in favour of `processing_class=`.

**Fix:** `patches/train.py.diff`

---

### P0-11 · `make wazuh-up` cannot work — certs are generated but never mounted

`scripts/generate_wazuh_certs.sh` writes to `docker/wazuh/config/wazuh_indexer_ssl_certs/`. `docker-compose.yml` has **no volume mounting that directory into any container**. The indexer's security plugin will not start without its certs; the manager runs Filebeat with `FILEBEAT_SSL_VERIFICATION_MODE=full` against an indexer that has no TLS.

The compose file also omits the `opensearch.yml` / `internal_users.yml` config mounts the upstream Wazuh single-node compose requires.

Two smaller defects in the same file:
* `x-wazuh-image-version: &wazuh-version "4.9.2"` — the anchor is defined and never referenced; both images hardcode `4.9.2`.
* `version: "3.8"` — obsolete in Compose v2, emits a warning on every invocation.

**Fix:** `patches/docker-compose.yml`

---

## P1 — Security

### P1-1 · APIM: tier is taken from a caller-supplied header, not the validated JWT

```xml
<validate-jwt ...>
  <required-claims><claim name="roles" match="any">
    <value>SOC.Tier1</value> ... <value>SOC.Admin</value>
  </claim></required-claims>
</validate-jwt>
...
<set-variable name="caller_tier"
  value="@(context.Request.Headers.GetValueOrDefault(&quot;X-SOC-Tier&quot;, &quot;tier1&quot;).ToLower())"/>
```

The policy validates that the caller holds *one of* four roles, then routes on a header the caller controls. A principal holding only `SOC.Tier1` sends `X-SOC-Tier: tier3` and reaches the Tier 3 batch backend. The role claim is checked for presence and never correlated with the tier it authorises.

This is broken access control, and the article documents it as the intended design ("Requests for processing are identified by the X-SOC-Tier header value"), so the article needs the same correction.

**Fix:** derive tier from the `roles` claim; keep `X-SOC-Tier` only as a downgrade request that is intersected with the claim. See `patches/soc_ai_policy.xml`.

### P1-2 · The ingestion API has no authentication at all

`POST /alerts/wazuh` accepts an arbitrary `dict` from anyone who can reach port 8000. There is no API key, no JWT, no mTLS, no IP allowlist. The Wazuh integration script is *handed* an API key by Wazuh and discards it:

```python
alert_file, _api_key = sys.argv[1], sys.argv[2]   # never used
```

In the compose topology the API is published on `0.0.0.0:8000`. In the AKS topology it sits behind APIM — but nothing prevents direct pod access, and APIM is the only thing checking the PHI header. Anyone who reaches the service directly bypasses the entire compliance layer.

### P1-3 · Prompt injection into a system that can isolate hosts

`full_log` is attacker-controlled — an attacker who can cause a log line can choose most of its content — and it is interpolated verbatim into the prompt. Verified:

```
attacker text reaches the prompt verbatim: True
```

Confidence is then parsed back out of the model's *free text* by regex, and that number gates automated containment at ≥ 0.85. The attack surface: craft a log line asserting a verdict and a confidence, and you can either suppress containment on a real intrusion or trigger containment on a critical host (a denial-of-service against your own estate, executed by your own SOC).

Parser behaviour, measured:

| Model output | Parsed |
|---|---|
| `Verdict: true positive. Confidence: 0.92` | `0.92` |
| `Escalate. confidence 0.4 ... reference case had confidence: 0.99` | `0.4` |
| `Certainty: 95%` | `0.3` |
| `Confidence: high` | `0.3` |

The fallback direction is correct (fail low, never auto-execute). But 0.3 is below `ESCALATION_CONFIDENCE_FLOOR = 0.6`, so **every unparseable generation silently escalates to a second LLM call**. Format drift doubles your inference bill with no signal.

**Fix:** delimit untrusted content, get confidence from a structured field rather than prose, and emit a parse-failure metric. See `patches/client.py` and `patches/prompts.py`.

### P1-4 · Internet-exposed Wazuh host with default credentials

```hcl
security_rule {
  name = "AllowSSH"
  destination_port_range = "22"
  source_address_prefix  = "*"      # the entire internet
}
security_rule {
  name = "AllowDashboardHTTPS"
  destination_port_range = "443"
  source_address_prefix  = "*"      # the entire internet
}
```

combined with:

```yaml
runcmd:
  - cd /opt/soc-ai && cp .env.example .env
```

```
WAZUH_API_PASSWORD=change-me
WAZUH_INDEXER_PASSWORD=change-me
```

Public SSH, public dashboard, and `change-me` credentials baked in at first boot. On a host holding a healthcare SIEM. Fix all three: scope the NSG to your admin CIDR, generate credentials into Key Vault in cloud-init, and don't publish 22 at all — use Bastion or a private endpoint.

The `AllowAgentEnrollment` rule is also written backwards:

```hcl
source_port_ranges     = ["1514", "1515"]   # these are DESTINATION ports
destination_port_range = "*"                # allows every port
```

### P1-5 · Root `terraform.tfstate` is not gitignored

`.gitignore` covers `infra/**/*.tfstate` and `infra/**/.terraform/`. It does **not** cover the repo root. The README's own instructions (`terraform init && terraform apply` from the root) put `terraform.tfstate` in an uncovered path. Terraform state contains secrets in plaintext — including, here, the Key Vault URI and `kube_config_raw`.

### P1-6 · `PhiTokenizer.__init__` will destroy every existing token

```python
try:
    secret = client.get_secret(encryption_key_secret)
    self.fernet = Fernet(secret.value.encode())
except Exception:
    new_key = Fernet.generate_key()
    client.set_secret(encryption_key_secret, new_key.decode())
```

A bare `except Exception` around a network call. A transient 503, a throttle, an expired token, a 403 from a misconfigured managed identity — any of these generates a **new** key and overwrites the existing one in Key Vault. Every PHI token ever issued becomes permanently undecryptable. Catch `ResourceNotFoundError` only.

### P1-7 · The correlation hash is brute-forceable

```python
prefix = hashlib.sha256(value.encode()).hexdigest()[:8]
```

An unsalted, unkeyed 8-hex-character (32-bit) hash of a PHI value, emitted in cleartext. For a constrained domain — SSNs, dates of birth, names from a patient roster, MRNs with a known format — the entire keyspace is exhaustible on a laptop. This is a re-identification channel that needs no Key Vault access at all, which defeats the point of holding the key in Key Vault.

Use `HMAC-SHA256` with a pepper stored in Key Vault, truncated to 16 hex chars.

### P1-8 · Secrets typed as plain `str`

```python
azure_client_secret: str | None = None
wazuh_api_password: str = Field(default="change-me")
```

`Settings` will happily `repr()` these into a traceback or a log line. Use `pydantic.SecretStr` for all five credential fields.

### P1-9 · Internal exception text returned to the caller

```python
except Exception as exc:
    raise HTTPException(status_code=500, detail=str(exc)) from exc
```

Returns stack-derived internal detail — file paths, connection strings in `httpx` errors, Key Vault URIs — to an unauthenticated client. Log the detail, return a correlation ID.

### P1-10 · Nothing can read Key Vault

Neither `main.tf` nor `infra/modules/key_vault/` creates a single `azurerm_key_vault_access_policy` or `azurerm_role_assignment`. `enable_rbac_authorization` is unset, so access policies apply — and there are none. The AKS pods, the Container App, the ML workspace, and Terraform itself all get 403.

`main.tf` compounds it with `network_acls { default_action = "Deny" }` and no `ip_rules` and no private endpoint. `bypass = "AzureServices"` does not cover AKS pod egress or Container Apps.

### P1-11 · Containers run as root, no `.dockerignore`

Both Dockerfiles: no `USER`, no `HEALTHCHECK`, no multi-stage build, no pinned base digest. There is no `.dockerignore`, so `docker build` ships `.git`, `.venv`, and any local `.env` into the build context — and `.env` into an image layer if a `COPY . .` is ever added.

For a repo whose subject is security tooling, this is the detail reviewers will notice first.

### P1-12 · `code="."` uploads the whole repo to Azure ML

`scripts/submit_azureml_finetune_job.py` snapshots the working directory. There is no `.amlignore`. A local `.env` with real credentials gets uploaded to the workspace storage account and retained with the job.

### P1-13 · `purge_protection_enabled = true` on a fixed-name Key Vault

`main.tf` sets purge protection with `name = "kv-socai-prod"`. Purge protection is irreversible on a vault. Anyone who deploys, evaluates, and destroys this reference implementation cannot redeploy it for 90 days. `infra/modules/key_vault` gets this right (`false`, 7 days, random suffix); the root file does not.

### P1-14 · Azure ML job inputs are declared but never referenced

```python
job = command(
    command="python src/llm/finetune/train.py --config src/llm/finetune/config.yaml",
    inputs={"train_data": Input(...), "eval_data": Input(...)},
)
```

The command string never uses `${{inputs.train_data}}`, so the mounts are ignored and `train.py` reads `./ml/data/*.jsonl` from the snapshot — which does not exist, because `ml/` is not in the repo (only `.gitignore` mentions it). The job fails at `load_dataset`.

---

## P2 — Correctness

| # | Location | Issue |
|---|---|---|
| P2-1 | `soc_ai_policy.xml` inbound/outbound | `X-SOC-Request-Id` is set as a **header** but read as a **variable**. `X-HIPAA-Audit-Id` is therefore always empty, and `context.Variables["X-SOC-Request-Id"]` in `on-error` throws `KeyNotFoundException` — the error handler itself errors, so the HIPAA audit trail is empty exactly when you need it. |
| P2-2 | `soc_ai_policy.xml` tier1 branch | `increment-condition="@(context.Response.StatusCode < 500)"` — `context.Response` is null during `inbound`. Throws at runtime. The tier2/tier3 branches correctly omit it. |
| P2-3 | `soc_ai_policy.xml` backend | Labelled "circuit breaker"; it is a retry. There is no circuit breaker (APIM has a real one on the backend entity). Three retries into an overloaded GPU backend is the classic retry storm, and the request being retried is a non-idempotent POST. The claimed "~2s, 8s, 30s" does not match `interval=2 delta=2 max-interval=30`. |
| P2-4 | `soc_ai_policy.xml` on-error | `log-to-eventhub logger-id="soc-audit-logger"` — no Event Hub and no APIM logger exists in any Terraform file. |
| P2-5 | `soc_ai_policy.xml` | `{TENANT_ID}` is a literal placeholder, and `{{tier1-mistral-container-app-url}}` etc. are named values never created by `azurerm_api_management_named_value`. There is also no `azurerm_api_management_api` — the policy has nothing to attach to. |
| P2-6 | `cost_alerts.json` alert 2 | Queries the Application Insights `customMetrics` table. APIM `emit-metric` writes to **Azure Monitor custom metrics**, a different store not queryable from Log Analytics KQL. The alert can never fire. |
| P2-7 | `cost_alerts.json` alert 3 | Fires on `ResponseCode == 400 and Message contains 'PHI-sanitized'` — that is the control **working**. A real bypass is PHI reaching the model *with* the header set, which this cannot see. Sev-0 paging on a client that forgot a header, and silence on the actual failure mode. |
| P2-8 | `cost_alerts.json` alert 4 | Monitors `KubeNodeInventory` for `aks-wazuh`. `infra/` deploys Wazuh on a **VM**. Only the non-parsing `main.tf` creates AKS. |
| P2-9 | `phi_tokenizer.py:_encrypt_token` | Fernet is non-deterministic (random IV + timestamp). Identical PHI values produce **different** tokens. The docstring's "identical PHI values produce the same token, enabling cross-event correlation" is false, and so is the article's paragraph on it. Only the 8-char prefix is stable — and that is the part that is brute-forceable (P1-7). |
| P2-10 | `phi_tokenizer.py:sanitize_alert` | `_walk` recurses every string in the alert, so `IP_ADDRESS` and `DATE_TIME` tokenize `data.srcip`, every timestamp, and `rule.description`. A triage model that cannot see the source IP or the time ordering cannot triage. Needs a field allowlist, not blanket recursion. |
| P2-11 | `phi_tokenizer.py:HIPAA_ENTITIES` | `"AGE"` is not a Presidio built-in entity. Unrecognised entity names are silently ignored, so ages are never detected despite the comment. |
| P2-12 | `phi_tokenizer.py` | Fernet ciphertext of a short string is ~100 chars, inlined into the log text. A sanitized alert can be 5–10× the original, which inflates prompt tokens and can overflow context. Emit `PHI_<TYPE>_<hmac16>` inline and keep ciphertext in a side table. |
| P2-13 | `main.tf` budget | `start_date = formatdate(..., timestamp())` — `timestamp()` is evaluated at plan time, so the value changes on every run. Perpetual diff, and `start_date` is `ForceNew`. |
| P2-14 | `tier3_response.py` | Returns `"status": "executed"` when nothing is executed. `docs/model_card.md` correctly says wiring active response is "a deliberate, separate integration point" — the status string contradicts the model card and would mislead an auditor reading the JSON. Use `"approved_for_execution"`. |
| P2-15 | `schema.py` | `timestamp: datetime = Field(default_factory=datetime.utcnow)` — deprecated in 3.12, and produces a *naive* datetime while `logging.py` produces tz-aware ones. Confirmed at runtime: `DeprecationWarning: datetime.datetime.utcnow() is deprecated`. Use `lambda: datetime.now(UTC)`. Same in `mlops_pipeline.py:register`. |
| P2-16 | `schema.py` | `rule_id=int(rule.get("id", 0))` — Wazuh emits rule IDs as strings and some rulesets use non-numeric IDs. A `ValueError` here becomes a 500 with the exception text (P1-9). |
| P2-17 | `evaluate.py` | Docstring promises "mean self-reported confidence calibration"; the function returns accuracy only. The gate in `mlops_pipeline.py` and the article both specify **precision ≥ 0.92 / recall ≥ 0.88** — neither is computed anywhere. Two different eval definitions, neither matching the gate. |
| P2-18 | `local_ml_decoders.xml` | Not well-formed XML — two sibling root `<decoder>` elements. Wazuh's own parser tolerates this (its stock `local_decoder.xml` looks the same), but `xmllint`, `defusedxml`, and any CI XML validation step will fail on it. Wrap in a container element or exclude it from XML linting deliberately. |
| P2-19 | `infra/modules/azure_ml/main.tf` | `resource "random_id" "suffix"` is declared and never referenced. |
| P2-20 | `.gitignore` | `infra/**/.terraform.lock.hcl` is ignored. The lock file **should** be committed — it is what pins provider versions reproducibly across the team and CI. |
| P2-21 | `alerts.py` | `@lru_cache def get_listener()` caches the listener across tests. `test_alerts_endpoint.py` patches `LlmInferenceClient` *before* the first request builds the chain — which works only because it happens to run first. Add a test that hits the endpoint before it and the suite breaks. Use FastAPI's `Depends` + `app.dependency_overrides` instead. |
| P2-22 | `docker-compose.yml` | Dashboard maps host `443:5601`, requiring root on Linux and colliding with anything else on 443. |
| P2-23 | `train.py` / `config.yaml` | LoRA targets only `q,k,v,o_proj`. For Mistral, adding `gate_proj/up_proj/down_proj` is the single highest-value change to adapter quality at r=16, for ~2× trainable params (still <1% of the model). `gradient_checkpointing` is not enabled, which you will want on a T4. |
| P2-24 | `mlops_pipeline.py` | Fails `ruff` (I001) and `black`. Neither the Makefile (`ruff check src tests`) nor pre-commit's practical reach covers the root files — the commit message is "Add files via upload", i.e. through the web UI, which bypasses pre-commit entirely. |

---

## P3 — Performance and cost

These matter because the article's headline is cost.

| # | Location | Issue and fix |
|---|---|---|
| P3-1 | `client.py` | A new `httpx.AsyncClient` per `generate()` call — new TCP + TLS handshake per LLM call, three per escalated alert. Hoist to a module-level client with a connection pool, closed in the app lifespan. At 1,000 alerts/min (the article's load-test target) this alone is significant. |
| P3-2 | `server.py` | `model.generate()` is a **blocking** call inside `async def generate()`. It runs on the event loop, so the inference server serialises every request and cannot even answer `/health` during a generation — Kubernetes will mark it unready and restart it mid-inference. Declare the endpoint `def` (FastAPI runs sync endpoints in a threadpool) or wrap in `run_in_threadpool`. **Highest-impact single fix in the repo.** |
| P3-3 | `server.py` | `_load_pipeline()` is lazy, so the *first request* pays a multi-minute model load — while blocking the event loop (P3-2). Preload in `lifespan` and let the readiness probe gate traffic. |
| P3-4 | `docker/api/Dockerfile` | Installs the full `requirements.txt`, including `torch==2.4.1` and `bitsandbytes`, into the FastAPI API image. ~2.5 GB for a service that needs fastapi + httpx + pydantic + azure SDKs. Split into `requirements-api.txt` / `requirements-ml.txt`. Cuts image pull time on every AKS scale-out. |
| P3-5 | `docker-compose.yml` `ml-inference` | `python:3.11-slim` on CPU, no GPU reservation, loading Mistral-7B in `bfloat16` — ~15 GB RAM and roughly 1 token/s. The documented local quickstart cannot run on a developer laptop. Also: `mistralai/Mistral-7B-Instruct-v0.2` is **gated** on HuggingFace and needs an accepted licence plus `HF_TOKEN`; there is no token in `.env.example` and no model cache volume, so every container recreate re-downloads ~15 GB. |
| P3-6 | `phi_tokenizer.py` | `analyzer.analyze()` is called once per string field via `_walk`. A Wazuh alert has dozens of string fields; Presidio NER is roughly 10–50 ms per call, so 0.5–2.5 s per alert single-threaded. This is the throughput ceiling of the whole pipeline. Fix: allowlist the 3–4 fields that can carry PHI, regex-prefilter before invoking NER, batch, and cache by field hash. |
| P3-7 | `soc_ai_policy.xml` | `counter-key="@(context.Request.IpAddress)"`. All alerts arrive from one Wazuh manager, i.e. one IP — so the entire SOC shares a single 1,000/min bucket, and one noisy source starves everything else. Key on the JWT `oid`/`sub`. |
| P3-8 | `soc_ai_policy.xml` | Rate limits but **no `quota-by-key`**. A runaway loop capped at 1,000/min still burns 1.44 M calls/day. The article's FinOps story needs an absolute daily ceiling, not just a rate. |
| P3-9 | `orchestrator.py` | Constructs three separate `LlmInferenceClient` instances (one per tier), each with its own settings lookup and, per P3-1, its own connection churn. Inject one. |
| P3-10 | `orchestrator.py` | Every escalated alert makes 2–3 sequential LLM calls with no deduplication. In a real SOC, the same rule fires hundreds of times an hour on near-identical logs. Cache triage results keyed on `(rule_id, agent, normalised log shape)` with a short TTL — likely a 5–20× reduction in Tier 1 inference cost, and the cheapest thing on this list. |
| P3-11 | `infra/modules/azure_ml` | `vm_priority = "Dedicated"` on `Standard_NC6s_v3` (V100, ~$3/hr on-demand). `main.tf` uses `LowPriority` on a T4. The article's FinOps section is built on spot pricing; the module that actually deploys contradicts it. |

---

## Recommended order of work

1. Resolve the README conflict and pick **one** architecture (P0-1). Everything else follows from this decision. My recommendation: keep `infra/` + `src/`, delete the root artifacts, and port the two genuinely valuable root pieces — the APIM policy and the FinOps alerts — into `infra/modules/`.
2. Fix the P0 blockers in this order: `main.tf` parse → cost alerts `scopes` → Wazuh rule chain + mount paths → cloud-init repo URL → compose cert mounts → train.py collator.
3. Add `.github/workflows/ci.yml` (`patches/github-workflows/ci.yml`). Once CI runs `terraform validate`, `xmllint`, `ruff`, and `pytest` on every push, the entire P0 class becomes impossible to reintroduce. This is the highest-leverage single change in the repo.
4. Wire the PHI boundary for real (P0-3) and switch APIM to derive tier from the JWT (P1-1). These two are what make the article's compliance claims true.
5. Then P3-2, P3-10, P3-4 — the three performance fixes with the best effort-to-impact ratio.

---

## What is genuinely good here

Worth saying, because the report is long and the signal-to-noise in `src/` is high:

* The comment style in `src/` explains **why**, not what — `tier3_response.py` on why containment needs a higher bar than classification, `client.py` on why the confidence fallback is conservative, `alert_listener.py` on why it is decoupled from FastAPI. That is unusually good.
* `infra/` is properly modularised, uses `random_id` for globally-unique names, keeps backend config out of the repo, and all 20 files parse.
* `docs/model_card.md` is honest — it explicitly says Tier 3 execution is not wired up. It is more accurate about the system than the README or the article.
* The tier abstraction (`SocTier`, `tier_from_wazuh_groups`, orchestrator escalation floor) is the right shape. It just is not connected at either end.
