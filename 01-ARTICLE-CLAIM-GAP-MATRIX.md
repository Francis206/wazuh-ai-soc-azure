# Article ↔ Repository Gap Matrix

The article closes with: *"The code repository mentioned at the end of this document contains the Terraform module code, the PHI Tokenizer pipeline code, Azure ML training code, APIM policy XML, FinOps alerting ARM templates, and the GitHub Actions workflow. The complete code is production-ready and deployable using a simple Terraform apply command."*

That sentence is the reason to read this table. A reader who clones the repo to check the article will hit a Terraform parse error on the first command.

Legend: **✅** implemented · **⚠️** partial or contradicted · **❌** absent

---

## Architecture

| # | Article claim | Repo | Notes |
|---|---|---|---|
| 1 | Wazuh on AKS via "a single Helm installation" | ❌ | No Helm chart, no values file, no `helm_release`. `infra/` deploys a **single VM** running docker-compose. `main.tf` creates an AKS cluster with **no workload deployed to it** — it comes up empty. |
| 2 | Mistral 7B on **Ollama** in Azure Container Apps | ⚠️ | `main.tf` has the Container App, but 2 vCPU / 4 GiB, CPU-only, `OLLAMA_MODELS=/mnt/models` with **no volume mounted** — the model re-downloads on every cold start. Meanwhile `src/llm/inference/server.py` implements a **transformers/PEFT** server, not Ollama. Two incompatible inference designs; neither matches the diagram. |
| 3 | Tier 2 RAG over **pgvector on Azure PostgreSQL Flexible Server**, retrieving MITRE ATT&CK, CVEs, internal runbooks | ❌ | No PostgreSQL resource, no pgvector, no embeddings, no retrieval code, no MITRE or CVE data source anywhere. `Tier2Investigation.investigate()` is a second LLM call, and the orchestrator passes `related_alerts=[]` **hardcoded** — so even the "related alerts in window" section of the prompt always renders `(none provided)`. |
| 4 | Tier 3 **Isolation Forest** nightly over the OpenSearch index | ❌ | No scikit-learn in `requirements.txt`, no anomaly-detection code, no scheduled job. |
| 5 | IOC correlation against **STIX/TAXII feeds from self-hosted OpenCTI** | ❌ | OpenCTI appears nowhere in the repo. |
| 6 | **Label Studio** for human annotation | ❌ | Appears nowhere in the repo. |
| 7 | Azure AD sign-in logs via the Wazuh Azure plugin; HL7/FHIR audit logs via custom XML decoders | ❌ | `wazuh/decoders/local_ml_decoders.xml` is two placeholder blocks with a comment saying "Add one `<decoder>` block per custom log source". No HL7, no FHIR, no Azure module config. This is the healthcare-specific ingestion the article leads with. |
| 8 | Blob lifecycle policy moving >90-day data to cold tier at ~$0.001/GB/mo | ❌ | No `azurerm_storage_management_policy` in either Terraform stack. |

## Compliance

| # | Article claim | Repo | Notes |
|---|---|---|---|
| 9 | "No AI model, training dataset, vector index, or report contains any PHI data" | ❌ | `phi_tokenizer.py` is imported by **nothing**. `grep -rn "phi_tokenizer\|presidio\|sanitiz\|PHI" src/ infra/ wazuh/ tests/ docker/ docs/` returns zero matches. Raw `full_log` goes straight into the prompt, and `dataset_prep.py` writes unsanitized alerts to the training set. |
| 10 | "SHA-256 hash prefixes are applied to the values before they are encrypted with AES-256, ensuring that if the same value is detected in multiple alerts, the token is the same" | ⚠️ | **The code does not do this.** Fernet is non-deterministic, so the token differs every call. Only the 8-char prefix is stable — and an unsalted 32-bit hash of an SSN or a name is exhaustible on a laptop, so the correlation handle is also a re-identification channel that needs no Key Vault access. Both the sentence and the implementation need correcting. |
| 11 | Any call missing `X-PHI-Sanitized: true` is rejected with HTTP 400 | ⚠️ | The policy does check the header. But the header is **self-asserted by the caller** and nothing upstream sets it, because nothing sanitizes. A control that the caller can satisfy by typing a string is not a boundary. |
| 12 | A missing header triggers a **Severity 0** Azure Monitor alert on "bypass of the security mechanism" | ⚠️ | The alert exists but is inverted: it fires when the control **blocks** a request, which is the control working. A genuine bypass — PHI reaching the model with the header set true — is undetectable by this rule. And the rule cannot deploy at all (no `scopes`, no action group). |
| 13 | Presidio detects biometric identifiers and health-insurance beneficiary numbers | ⚠️ | Neither is in `HIPAA_ENTITIES`, and Presidio has no built-in recognizer for either. `"AGE"` is in the list but is **not a Presidio entity** — unrecognised names are silently dropped, so ages are never detected. |
| 14 | Detokenization requires Key Vault read access via Azure RBAC | ⚠️ | True in principle, but neither Terraform stack creates a single access policy or role assignment on the vault, and `main.tf` sets `network_acls.default_action = "Deny"` with no exceptions. Nothing — including Terraform — can read it. |
| 15 | 401s are logged to Event Hub for the HIPAA audit trail | ❌ | No Event Hub namespace, no hub, no `azurerm_api_management_logger` in any `.tf` file. `log-to-eventhub logger-id="soc-audit-logger"` references something that does not exist, and the handler containing it throws before reaching it (see report P2-1). |

## MLOps

| # | Article claim | Repo | Notes |
|---|---|---|---|
| 16 | Weekly Azure ML pipeline: data prep → PHI consistency check → dedupe → 80/20 split → LoRA → gate → MLflow | ⚠️ | `mlops_pipeline.py` declares the shape but points at `./components/{data_prep,finetune,evaluate}` — **none of which exist**. No PHI consistency check and no dedupe step in any implementation. No schedule. `register()` (the MLflow step) is defined and never called. |
| 17 | Gate discards models below **precision 0.92 / recall 0.88** | ❌ | `evaluate.py` computes **accuracy only**; precision and recall are computed nowhere in the repo. Three different eval definitions across `evaluate.py`, `mlops_pipeline.py`, and `docs/model_card.md`. |
| 18 | Seeded with CIC-IDS-2017 (2.8 M flows) + UNSW-NB15 (2.5 M) + GPT-4o-synthesised rare-attack alerts | ❌ | No download script, no loader, no synthesis prompt, no dataset card. `dataset_prep.py` expects a JSONL of analyst-labeled Wazuh alerts, which is a different input than either public dataset. This is the article's answer to the cold-start problem and it has no code. |
| 19 | Model runs in **shadow mode** for months 1–2 | ❌ | No shadow-mode flag, config, or code path. Out of the box, `CONFIDENCE_THRESHOLD = 0.85` and Tier 3 sets `auto_execute=True` immediately. |
| 20 | Confidence threshold starts at 90% and is lowered as the model proves out | ❌ | Hardcoded to `0.85` as a module constant. Not configurable, not in `.env.example`, not in `config.yaml`. |
| 21 | Spot preemption resumes from the previous checkpoint | ⚠️ | `TrainingArguments` sets `save_strategy` from config (`epoch`) but never sets `resume_from_checkpoint`, and `trainer.train()` is called with no arguments. A preempted job restarts from scratch. |
| 22 | Blue/green deployment of application containers | ⚠️ | `main.tf` sets `revision_mode = "Multiple"` on the Container App — the enabling flag, not the mechanism. No traffic-split logic, no promotion step, no rollback. |

## APIM control plane

| # | Article claim | Repo | Notes |
|---|---|---|---|
| 23 | JWT role claim (`SOC.Tier1/2/3/Admin`) determines authorisation | ⚠️ | The role is validated for **presence** and then never used. Routing and rate limiting key off the caller-supplied `X-SOC-Tier` header. A `SOC.Tier1` principal reaches the Tier 3 backend by changing a header. See report P1-1 — this is the security bug that most needs fixing in **both** the code and the article. |
| 24 | Per-tier rate limits 1,000 / 200 / 50 per minute | ⚠️ | Present, but keyed on `context.Request.IpAddress`. All alerts originate from one Wazuh manager, so the whole SOC shares one bucket. |
| 25 | "Opens a circuit breaker for further requests" | ❌ | It is a `<retry>`, not a circuit breaker. No `circuitBreaker` configuration on any APIM backend. Three retries of a non-idempotent POST into a saturated GPU backend makes an outage worse. |
| 26 | Gateway retrieves secrets from Key Vault at runtime via Managed Identity | ❌ | The APIM resource in `main.tf` has **no `identity` block**, no Key Vault access policy, and no `azurerm_api_management_named_value` with `key_vault_id`. The `{{tier1-mistral-container-app-url}}` named values referenced by the policy are never created. |
| 27 | `ai_call_count` increments in Azure Monitor; alert at >500 k/hour | ⚠️ | `emit-metric` is correct. The alert querying it is not — it reads the Application Insights `customMetrics` table, a different store. The alert can never fire. |
| 28 | The policy is deployable | ❌ | There is no `azurerm_api_management_api`, no operation, and no `azurerm_api_management_api_policy` resource. The XML has nothing to attach to. `{TENANT_ID}` is a literal placeholder. |

## CI/CD

| # | Article claim | Repo | Notes |
|---|---|---|---|
| 29 | Five-stage GitHub Actions pipeline | ❌ | **No `.github/` directory exists.** Referenced 6 times across the README, both docs, `train.py`, `config.yaml`, `evaluate.py`, and a test docstring. |
| 30 | OIDC federation, no static credentials | ❌ | — |
| 31 | Trivy scans for container and Terraform IaC misconfiguration | ❌ | — |
| 32 | `pytest` tests for the PHI tokenizer and APIM policy schema | ❌ | Zero tests for either. `phi_tokenizer.py` has no test file at all, and the APIM XML is validated nowhere. |
| 33 | Load test at 1,000 alerts/min | ❌ | No load-test harness. (And per report P3-2, the inference server serialises requests on the event loop, so it would not survive one.) |
| 34 | Environment protection rule requiring a named security engineer's approval | ❌ | — |
| 35 | Helm rolling update, Container App revision switch, smoke test with auto-rollback | ❌ | — |

## Cost

| # | Source | Figure |
|---|---|---|
| 36 | Article, Key Takeaways | **$350–$800/month** for 50 endpoints |
| 37 | README (surviving half) | **$180–$4,500/month** depending on endpoint count |
| 38 | `main.tf` budget | **$800** (`asset_count < 100`) / **$2,000** |
| 39 | `infra/modules/azure_ml` | `Dedicated` `Standard_NC6s_v3` — V100 on-demand, ~$3/hr, which contradicts the article's entire spot-pricing FinOps argument |

Four numbers, no two of which agree. Whichever is right, they should all be derived from one place.

## Citation

| # | Article text | Note |
|---|---|---|
| 40 | "According to the 2023 ISC² Cybersecurity Workforce Study, there is a global talent shortage of around 3.4 million" — cited with the URL `isc2.org/Insights/2025/12/2025-ISC2-Cybersecurity-Workforce-Study` | The prose cites the 2023 study; the link points at the 2025 study. The 3.4 M figure is from the 2022/2023 reporting cycle. Either update the number to match the 2025 study you linked, or cite the 2023 report you quoted. Worth fixing — it is in the first paragraph, and it is the kind of thing a reviewer checks first. |

---

## The four changes that close most of the gap

You do not need to build pgvector RAG and Isolation Forest to make the article honest. In rough order of return:

1. **Wire the PHI boundary.** It is one module and two call sites (`alert_listener.handle_raw_alert`, `dataset_prep.build_examples`). It converts claims 9, 10, 11 and 12 from false to true, and it is the claim the whole healthcare framing rests on. `patches/src_common_phi.py`.
2. **Add `.github/workflows/ci.yml`.** Claim 29 becomes partially true immediately, and CI would have caught P0-1, P0-2, P0-8, P0-9 and P0-10 before they were ever pushed. `patches/github-workflows/ci.yml`.
3. **Derive the APIM tier from the JWT role.** Claim 23 is currently a documented privilege-escalation path. `patches/soc_ai_policy.xml`.
4. **Add a "Not yet implemented" section to the README** listing pgvector RAG, Isolation Forest, OpenCTI, Label Studio, and the seed datasets, and change the article's closing sentence from "production-ready" to "reference implementation". A repo that is honest about its scope is more credible than one that overclaims — and as a Wazuh Ambassador publishing under your own name, that credibility is the asset. The architecture in the article is genuinely good; the gap is that the repo does not yet back it.
