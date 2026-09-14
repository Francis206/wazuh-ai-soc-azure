# Open-Source AI-Augmented SOC on Azure

Automating Tier 1–3 SOC operations by pairing **Wazuh** (open-source SIEM/XDR)
with **fine-tuned open-weight LLMs** served from **Azure ML**, wired together by
an alert-processing and automation pipeline.

Companion codebase for [*Open-Source AI-Augmented SOC on Azure: Automating
Tier 1-3 SOC Operations with Fine-Tuned LLMs*](https://medium.com/@francisAg/open-source-ai-augmented-soc-on-azure-automating-tier-1-3-soc-operations-with-fine-tuned-llms-4ff1f9a22adc)
— Francisco Agballog, Medium, April 2026.

> **Status: reference implementation, not production-ready.** See
> [What's not implemented](#whats-not-implemented) before deploying. Do not
> run this against real PHI without completing the 45 CFR §164.514(b)
> de-identification risk assessment yourself.

<!--
  This file replaces a committed merge conflict. The version on main begins
  with `<<<<<<< HEAD` and ends with `>>>>>>> 887ba77...`, so GitHub renders
  only the second half — which advertises a terraform/, python/, apim/,
  finops/ layout that does not exist, and states the article was published
  on InfoQ rather than Medium.

  The two halves described two different architectures. This resolution
  keeps the src/ + infra/ one and treats the root-level files as the
  article's standalone artifacts, which is what they are.
-->

## What's here

| Layer | Purpose | Path |
|---|---|---|
| SIEM | Wazuh manager / indexer / dashboard | `docker/`, `wazuh/` |
| Ingestion | Normalizes Wazuh alerts into the pipeline | `src/ingestion/` |
| LLM | Fine-tunes and serves an open-weight model (LoRA/QLoRA) on Azure ML | `src/llm/` |
| Automation | Tier 1 triage, Tier 2 investigation, Tier 3 response | `src/soc_automation/` |
| API | FastAPI service exposing the pipeline | `src/api/` |
| Infra | Terraform for all Azure resources | `infra/` |

### Article artifacts

These four files back specific sections of the article. They are standalone —
the pipeline in `src/` does not import them.

| File | Article section |
|---|---|
| `main.tf` | Infrastructure as Code: One Module, Multiple Scalings |
| `phi_tokenizer.py` | HIPAA Compliance: Establishing the PHI Border |
| `soc_ai_policy.xml` | Azure API Management as the AI Control Plane |
| `cost_alerts.json` | FinOps alerting |

See [`docs/architecture.md`](docs/architecture.md) for the design and
[`docs/deployment.md`](docs/deployment.md) to stand it up.

## Quick start (local dev)

```bash
cp .env.example .env
# Set at minimum: WAZUH_INDEXER_PASSWORD, WAZUH_DASHBOARD_PASSWORD, HF_TOKEN,
# PHI_PEPPER (openssl rand -hex 32). The stack will refuse to start otherwise.

make setup                      # venv, deps, pre-commit hooks
./scripts/generate_wazuh_certs.sh
make wazuh-up                   # Wazuh manager/indexer/dashboard
make api                        # FastAPI automation service on :8000
make test
```

Dashboard: <https://localhost:8443> (self-signed). API docs:
<http://localhost:8000/docs>.

**Hardware note.** `ml-inference` loads Mistral-7B in bfloat16 on CPU — roughly
15 GB of RAM at about 1 token/s. For laptop development, point
`LLM_INFERENCE_URL` at a remote endpoint, or substitute Ollama with a quantised
GGUF, which is what the article's Container Apps tier actually uses.
`mistralai/Mistral-7B-Instruct-v0.2` is a gated model: accept the licence on
HuggingFace and set `HF_TOKEN`.

## Deploying to Azure

See [`docs/deployment.md`](docs/deployment.md). Terraform state lives in a
storage account you create once out of band; `infra/backend.tf` takes its
config at `terraform init` time so the same code serves dev/staging/prod.

```bash
cd infra
terraform init -backend-config=environments/dev.backend.hcl
terraform plan -var-file=environments/dev.tfvars
```

**Before you apply**, review `infra/modules/networking/main.tf`. The NSG
currently allows SSH and HTTPS from `0.0.0.0/0`, and cloud-init copies
`.env.example` verbatim — so the Wazuh host comes up internet-facing with
`change-me` credentials. Scope `admin_cidrs` to your own ranges and provision
credentials into Key Vault before exposing anything.

## Cost

Azure resources only; Wazuh, Mistral 7B, Presidio, OpenCTI and Label Studio
carry no licence fee.

| Endpoints | Monthly |
|---|---|
| 50 | $350–800 |
| 500 | (measure it) |

The dominant line item is the always-on compute hosting Wazuh. The GPU cluster
scales to zero after 10 minutes idle and runs roughly six hours a week, so
training is not the driver. APIM Developer SKU is ~$49/mo with no SLA; Standard
is ~$280/unit/mo with 99.95%.

<!--
  These figures previously disagreed across four places: the article said
  $350-800, this README said $180-4,500, main.tf budgeted 800/2000, and
  infra/modules/azure_ml provisioned a Dedicated NC6s_v3 (V100, ~$3/hr) that
  contradicts the spot-pricing argument entirely. Pick one source of truth
  and derive the rest from it.
-->

## Compliance

- HIPAA Safe Harbor de-identification via Microsoft Presidio
- PHI boundary enforced before any alert reaches a model or a training set
- Audit correlation ID on every gateway response
- 45 CFR §164.514(b) de-identification risk assessment required before
  production use — Presidio does not cover all 18 Safe Harbor identifiers
  natively; device serial numbers and organization-specific identifiers need
  custom recognizers

## What's not implemented

The article describes the full target architecture. The repo implements part of
it. Listing the gap is more useful than leaving readers to discover it:

| Described | Status |
|---|---|
| Wazuh on AKS via Helm | Not implemented — `infra/` deploys a single VM running docker-compose |
| Tier 2 RAG over pgvector (MITRE ATT&CK, CVEs, runbooks) | Not implemented — Tier 2 is a second LLM call with no retrieval |
| Tier 3 Isolation Forest anomaly detection | Not implemented |
| OpenCTI STIX/TAXII IOC correlation | Not implemented |
| Label Studio annotation loop | Not implemented |
| CIC-IDS-2017 / UNSW-NB15 seed datasets | No loader or download script |
| Shadow mode (months 1–2) | Not implemented — `CONFIDENCE_THRESHOLD` is a hardcoded `0.85` |
| GitHub Actions five-stage pipeline | Partial — quality gate only, no deploy stages |
| HL7/FHIR audit log decoders | Placeholder decoders only |
| Wazuh active-response execution | Deliberately not wired. `Tier3Response` returns a recommendation; see [`docs/model_card.md`](docs/model_card.md) before connecting anything that can isolate a host |

## License

MIT — see [`LICENSE`](LICENSE).
