# Model Card: SOC Tier 1-3 Assistant

## Overview

Fine-tuned adapter (LoRA) on top of an open-weight base model, trained to
triage, investigate, and recommend response actions for Wazuh security
alerts. See `src/llm/finetune/config.yaml` for exact hyperparameters.

| | |
|---|---|
| Base model | `mistralai/Mistral-7B-Instruct-v0.2` (configurable) |
| Fine-tuning method | QLoRA (4-bit NF4 quantization, LoRA r=16) |
| Training data | Analyst-labeled historical Wazuh incidents (not included in this repo — see `docs/deployment.md` §4) |
| Intended use | Tier 1 triage summaries, Tier 2 correlation narratives, Tier 3 containment *recommendations* |
| Out of scope | Fully autonomous Tier 3 execution below the confidence threshold; non-security-domain tasks |

## Evaluation

`src/llm/evaluation/evaluate.py` reports triage-classification accuracy
against a held-out set. Re-run after every fine-tuning job
(`ml-training.yml` does this automatically) and record the numbers in the
PR that changes `src/llm/finetune/config.yaml` or the training data.

## Safety considerations

- Tier 3 responses only auto-execute when the model's self-reported
  confidence is ≥ `CONFIDENCE_THRESHOLD` (0.85, see
  `src/soc_automation/tier3_response.py`). Below that, the action is queued
  for human approval — never executed automatically.
- Prompts explicitly instruct the model not to fabricate IOCs and to ground
  claims in the evidence provided (`src/llm/inference/prompts.py`).
- The model has no direct ability to execute containment actions itself;
  `Tier3Response` only returns a *recommendation* plus a status field, and
  wiring that to a real Wazuh active-response call is a deliberate,
  separate integration point — review `src/soc_automation/tier3_response.py`
  before connecting it to anything that can actually isolate a host.

## Retraining

Retrain when: false-positive/false-negative rates from human review exceed
your organization's threshold, Wazuh rule sets change meaningfully, or a
new attack pattern needs representation in the training set.
