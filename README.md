<<<<<<< HEAD
# Open-Source AI-Augmented SOC on Azure

Automating Tier 1–3 SOC operations by pairing **Wazuh** (open-source SIEM/XDR)
with **fine-tuned open-source LLMs** served from **Azure ML**, wired together
by an alert-processing and automation pipeline.

Companion codebase for the article:
[*Open-Source AI-Augmented SOC on Azure: Automating Tier 1-3 SOC Operations
with Fine-Tuned LLMs*](https://medium.com/@francisAg/open-source-ai-augmented-soc-on-azure-automating-tier-1-3-soc-operations-with-fine-tuned-llms-4ff1f9a22adc).

## What's here

| Layer | Purpose | Path |
|---|---|---|
| SIEM | Wazuh manager / indexer / dashboard | `docker/`, `wazuh/` |
| Ingestion | Normalizes Wazuh alerts into the pipeline | `src/ingestion/` |
| LLM | Fine-tunes and serves an open-weight model (LoRA/QLoRA) on Azure ML | `src/llm/` |
| Automation | Tier 1 triage, Tier 2 investigation, Tier 3 response | `src/soc_automation/` |
| API | FastAPI service exposing the pipeline | `src/api/` |
| Infra | Terraform for all Azure resources | `infra/` |
| CI/CD | Lint, test, build, security scan, Terraform, Azure ML training | `.github/workflows/` |

See [`docs/architecture.md`](docs/architecture.md) for the full design and
[`docs/deployment.md`](docs/deployment.md) to stand it up end to end.

## Quick start (local dev)

```bash
cp .env.example .env
make setup        # create venv, install deps, pre-commit hooks
make wazuh-up      # start Wazuh manager/indexer/dashboard via docker-compose
make api           # run the FastAPI automation service locally
make test          # run unit + integration tests
```

## Deploying to Azure

CI/CD is gated on GitHub secrets so the pipeline is safe to merge before any
cloud credentials exist. See [`docs/deployment.md`](docs/deployment.md) for
the exact secrets to add (`AZURE_CREDENTIALS`, `AZURE_SUBSCRIPTION_ID`,
`TF_STATE_*`) — once present, the `terraform.yml` and `ml-training.yml`
workflows deploy automatically; until then, everything else (lint, tests,
image builds, security scans) still runs on every PR.

## Repository layout

```
.
├── docker/                # Dockerfiles + Wazuh compose config
├── wazuh/                 # Custom rules, decoders, alert integrations
├── src/
│   ├── ingestion/          # Wazuh alert listener + normalization
│   ├── llm/                # Fine-tuning, inference server, evaluation
│   ├── soc_automation/     # Tier 1/2/3 automation logic
│   ├── api/                # FastAPI app
│   └── common/             # Shared config, logging, Azure clients
├── infra/                 # Terraform modules + environments (dev/prod)
├── ml/                    # Data/notebooks/model artifacts (gitignored data)
├── tests/                 # Unit + integration tests
├── scripts/                # Dev/deploy/cert/training helper scripts
└── docs/                  # Architecture, deployment, model card
```

## License

MIT — see [`LICENSE`](LICENSE).
=======
# wazuh-ai-soc-azure

Open-source AI-augmented Security Operations Center on Azure — replacing 
Tier 1–3 analyst functions with fine-tuned LLMs, at SMB-accessible cost.

> Published on InfoQ DevOps/Cloud · April 2026  
> Author: Francisco Agballog · Wazuh Ambassador

## What this is

A production-ready reference implementation of an AI-powered SOC built 
entirely on open-source tooling and Azure-native services. The stack 
covers Tier 1 alert triage, Tier 2 incident investigation, and Tier 3 
threat hunting autonomously — with a PHI boundary enforced in code at 
every layer for HIPAA compliance.

**Infrastructure cost:** $180–$4,500/month depending on endpoint count.  
**Licensing cost:** $0 — Wazuh, Mistral 7B, Presidio, OpenCTI, and 
Label Studio are all open-source.

## Files in this repo

| File | Purpose |
|---|---|
| `terraform/main.tf` | Full Azure infrastructure — AKS, APIM, Azure ML, Key Vault, budget alerts. Single `asset_count` variable scales from dental practice to regional hospital. |
| `python/phi_tokenizer.py` | HIPAA PHI tokenization using Microsoft Presidio + Azure Key Vault. AES-256 Fernet encryption with SHA-256 hash prefix for cross-event correlation. |
| `python/mlops_pipeline.py` | Azure ML LoRA fine-tuning pipeline with eval gate (precision >92%, recall >88%) and MLflow model registry integration. |
| `apim/soc_ai_policy.xml` | Azure API Management policy — JWT auth, X-PHI-Sanitized header enforcement, per-tier rate limiting (1000/200/50 calls/min), circuit breaker, and `ai_call_count` metering. |
| `finops/cost_alerts.json` | ARM template for Azure Monitor alert rules — GPU runaway detection, PHI bypass severity-0 alert, SIEM offline alert, APIM call spike. |

## Deploy
```bash
terraform init
terraform apply -var="asset_count=50"
```

Full walkthrough in the companion InfoQ article.

## Compliance

- HIPAA Safe Harbor de-identification via Microsoft Presidio
- PHI boundary enforced at APIM gateway (HTTP 400 on bypass)  
- Severity-0 Azure Monitor alert on any sanitization bypass
- 45 CFR §164.514(b) de-identification risk assessment required for production
- All training data is PHI-sanitized before reaching Azure ML
>>>>>>> 887ba77effca7e9ef0020a4c8f2a6b687fa245d2
