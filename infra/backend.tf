# Remote state backend. Values are supplied at `terraform init` time via
# `-backend-config=environments/<env>.backend.hcl` (see docs/deployment.md)
# rather than hardcoded here, so the same config works for dev/staging/prod
# state without editing this file.
terraform {
  backend "azurerm" {}
}
