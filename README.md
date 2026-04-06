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
