# Deployment

## Local development

```bash
./scripts/setup_dev.sh          # venv + deps + pre-commit
./scripts/generate_wazuh_certs.sh
make wazuh-up                    # Wazuh manager/indexer/dashboard
make api                         # FastAPI automation service on :8000
```

Dashboard: https://localhost (self-signed cert, default creds in
`.env.example` — change them). API docs: http://localhost:8000/docs.

## Deploying to Azure

### 1. One-time: Terraform state backend

Terraform's own state has to live somewhere before `terraform init` can run
against this repo's `infra/backend.tf`. Create it once, out of band:

```bash
az group create -n rg-tfstate -l eastus
az storage account create -n sttfstatesocai -g rg-tfstate -l eastus --sku Standard_LRS
az storage container create -n tfstate --account-name sttfstatesocai
```

### 2. GitHub secrets

Add these under **Settings → Secrets and variables → Actions**. Until they
exist, `terraform.yml` and `ml-training.yml` print a skip notice and no-op —
everything else in CI still runs.

| Secret | Value |
|---|---|
| `AZURE_CLIENT_ID` | App registration / federated identity client ID |
| `AZURE_TENANT_ID` | Azure AD tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Target subscription |
| `TF_STATE_RESOURCE_GROUP` | `rg-tfstate` |
| `TF_STATE_STORAGE_ACCOUNT` | `sttfstatesocai` |
| `TF_STATE_CONTAINER` | `tfstate` |
| `WAZUH_SSH_PUBLIC_KEY` | SSH public key for the Wazuh VM admin user |
| `AZURE_RESOURCE_GROUP` | App resource group name (post-`terraform apply`) |
| `AZURE_ML_WORKSPACE` | Azure ML workspace name (post-`terraform apply`) |

Prefer OIDC federated credentials over a client secret: `azure/login@v2`
in `terraform.yml`/`ml-training.yml` is already configured for it
(`id-token: write` permission is set) — see
[Azure's GitHub OIDC guide](https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect).

### 3. Provision infrastructure

Once secrets are set, pushing to `main` with changes under `infra/`
triggers `terraform.yml`: it plans on PRs (commenting on the PR) and
applies on merge to `main`, gated by the `dev` GitHub Environment (add
required reviewers there for a manual approval gate).

To run it locally instead:

```bash
cp infra/environments/dev.tfvars.example infra/environments/dev.tfvars
cp infra/environments/dev.backend.hcl.example infra/environments/dev.backend.hcl
# edit both with real values
make infra-plan
make infra-apply
```

### 4. Fine-tune the model

`ml-training.yml` submits `src/llm/finetune/train.py` as an Azure ML
command job on the `gpu-cluster` compute (provisioned by
`infra/modules/azure_ml`, autoscales from 0). Prepare labeled data first:

```bash
python -m src.llm.finetune.dataset_prep --input path/to/labeled_incidents.jsonl
```

Then push changes under `src/llm/finetune/` or `ml/data/` to `main`, or run
the workflow manually via `workflow_dispatch`.

### 5. Point the pipeline at Azure

Update `.env` (or the app's Azure App Configuration/Key Vault references)
with the deployed Wazuh VM IP, Azure ML endpoint URL, and Key Vault name
from `terraform output`.
