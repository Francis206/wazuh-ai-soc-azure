# =============================================================================
# main.tf — corrected. Changes vs the committed version:
#
#   PARSE ERRORS (the file did not parse at all before these three):
#     L102 env { name = "...", value = "..." }              -> separate lines
#     L110 traffic_weight { percentage = 100, latest... }   -> separate lines
#     L198 output "aks_kube_config" { value = ..., sensi... } -> separate lines
#   HCL allows commas inside object *expressions* (tags = { a = 1, b = 2 })
#   but never between arguments in a *block body*.
#
#   DEPLOYMENT BLOCKERS:
#     - Key Vault had network_acls default_action=Deny with no exceptions and
#       zero access policies -> nothing, including Terraform, could read it.
#     - Globally-unique names (kv-, st-, apim-) had no random suffix -> the
#       second person to deploy this collides.
#     - purge_protection_enabled=true on a fixed name -> cannot redeploy for
#       90 days after a destroy. Now defaulted off, opt-in via variable.
#     - budget start_date used timestamp() -> changed every plan, and the
#       field is ForceNew. Now an explicit variable.
#     - Ollama container had no volume for OLLAMA_MODELS -> re-downloaded the
#       model on every cold start. Now backed by an Azure Files share.
#     - APIM had no managed identity and no named values, so the policy in
#       soc_ai_policy.xml had nothing to resolve {{...}} against.
#
#   STILL YOUR CALL (deliberately not changed):
#     - The AKS cluster is created with no Wazuh workload deployed to it.
#       Add a helm_release or delete the cluster; an empty AKS node pool is
#       the single largest line item in the article's cost table.
#     - 2 vCPU / 4 GiB CPU-only is not enough to serve Mistral 7B at SOC
#       volume. See report P3-5.
# =============================================================================

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "azurerm" {}
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = !var.key_vault_purge_protection
      recover_soft_deleted_key_vaults = true
    }
  }
  subscription_id = var.subscription_id
}

# ── Variables ────────────────────────────────────────────────────────────────

variable "subscription_id" {
  description = "Target Azure subscription"
  type        = string
}

variable "location" {
  type    = string
  default = "eastus2"
}

variable "env" {
  type    = string
  default = "prod"
}

variable "asset_count" {
  description = "Endpoint count. Drives AKS/GPU SKU selection and budget."
  type        = number
  default     = 50
}

variable "budget_start_date" {
  description = <<-EOT
    First day of the budget period, RFC3339, e.g. 2026-10-01T00:00:00Z.
    Must be the first of a current or future month. Set explicitly rather
    than derived from timestamp(), which produces a perpetual diff on a
    ForceNew field.
  EOT
  type        = string
}

variable "admin_cidrs" {
  description = "CIDRs permitted to reach Key Vault. Your deployer/CI egress."
  type        = list(string)
  default     = []
}

variable "key_vault_purge_protection" {
  description = <<-EOT
    Purge protection is IRREVERSIBLE once enabled on a vault. Leave false for
    evaluation deployments; set true only for a production vault you will not
    be tearing down.
  EOT
  type    = bool
  default = false
}

variable "alert_email" {
  description = "Recipient for budget and cost alerts"
  type        = string
}

# ── Locals ───────────────────────────────────────────────────────────────────

locals {
  prefix = "socai-${var.env}"

  tags = {
    environment = var.env
    compliance  = "hipaa-nist"
    owner       = "soc-team"
  }

  aks_vm_sku = var.asset_count < 100 ? "Standard_DS2_v2" : "Standard_DS4_v2"
  ml_vm_sku  = var.asset_count < 100 ? "Standard_NC4as_T4_v3" : "Standard_NC8as_T4_v3"
}

data "azurerm_client_config" "current" {}

resource "random_id" "suffix" {
  byte_length = 3
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.prefix}"
  location = var.location
  tags     = local.tags
}

# ── Key Vault — PHI encryption keys and all secrets ──────────────────────────

resource "azurerm_key_vault" "main" {
  name                       = substr("kv-${replace(local.prefix, "-", "")}${random_id.suffix.hex}", 0, 24)
  resource_group_name        = azurerm_resource_group.main.name
  location                   = var.location
  sku_name                   = "standard"
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  purge_protection_enabled   = var.key_vault_purge_protection
  soft_delete_retention_days = 90
  enable_rbac_authorization  = true
  tags                       = local.tags

  network_acls {
    bypass         = "AzureServices"
    default_action = length(var.admin_cidrs) > 0 ? "Deny" : "Allow"
    ip_rules       = var.admin_cidrs
  }
}

# Without this, nothing could read the vault -- not the pipeline, not the
# PhiTokenizer, not Terraform itself. The committed version had no access
# policy and no role assignment of any kind.
resource "azurerm_role_assignment" "kv_deployer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "kv_aks" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_kubernetes_cluster.wazuh.kubelet_identity[0].object_id
}

resource "azurerm_role_assignment" "kv_apim" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_api_management.main.identity[0].principal_id
}

# ── Log Analytics — central SIEM and audit store ─────────────────────────────

resource "azurerm_log_analytics_workspace" "main" {
  name                = "law-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = 90
  tags                = local.tags
}

# ── AKS — Wazuh SIEM/XDR cluster ─────────────────────────────────────────────

resource "azurerm_kubernetes_cluster" "wazuh" {
  name                = "aks-wazuh-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  dns_prefix          = "wazuh-${var.env}"
  tags                = local.tags

  default_node_pool {
    name            = "system"
    node_count      = var.asset_count < 100 ? 2 : 3
    vm_size         = local.aks_vm_sku
    os_disk_size_gb = 128
  }

  identity {
    type = "SystemAssigned"
  }

  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  }

  # network_policy added: without it there is no pod-level segmentation,
  # which is hard to defend in a HIPAA review.
  network_profile {
    network_plugin    = "azure"
    network_policy    = "calico"
    load_balancer_sku = "standard"
  }
}

# ── Container Apps — Ollama/Mistral inference (Tier 1) ───────────────────────

resource "azurerm_container_app_environment" "inference" {
  name                       = "cae-inference-${local.prefix}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = var.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

# Model weights persist here instead of being re-pulled on every cold start.
resource "azurerm_storage_share" "models" {
  name               = "ollama-models"
  storage_account_id = azurerm_storage_account.ml.id
  quota              = 100
}

resource "azurerm_container_app_environment_storage" "models" {
  name                         = "ollama-models"
  container_app_environment_id = azurerm_container_app_environment.inference.id
  account_name                 = azurerm_storage_account.ml.name
  share_name                   = azurerm_storage_share.models.name
  access_key                   = azurerm_storage_account.ml.primary_access_key
  access_mode                  = "ReadWrite"
}

resource "azurerm_container_app" "mistral_tier1" {
  name                         = "ca-mistral-t1-${local.prefix}"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.inference.id
  revision_mode                = "Multiple"
  tags                         = local.tags

  template {
    container {
      name   = "ollama-mistral"
      image  = "ollama/ollama:latest"
      cpu    = 2.0
      memory = "4Gi"

      # FIXED: was `env { name = "...", value = "..." }` on one line.
      env {
        name  = "OLLAMA_MODELS"
        value = "/mnt/models"
      }

      volume_mounts {
        name = "models"
        path = "/mnt/models"
      }
    }

    volume {
      name         = "models"
      storage_name = azurerm_container_app_environment_storage.models.name
      storage_type = "AzureFile"
    }

    min_replicas = 1
    max_replicas = var.asset_count < 100 ? 3 : 6
  }

  ingress {
    external_enabled = false
    target_port      = 11434

    # FIXED: was `traffic_weight { percentage = 100, latest_revision = true }`.
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}

# ── Azure ML — training workspace ────────────────────────────────────────────

resource "azurerm_storage_account" "ml" {
  name                            = substr("stsocml${var.env}${random_id.suffix.hex}", 0, 24)
  resource_group_name             = azurerm_resource_group.main.name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

resource "azurerm_application_insights" "main" {
  name                = "ai-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = local.tags
}

resource "azurerm_machine_learning_workspace" "main" {
  name                    = "mlw-${local.prefix}"
  resource_group_name     = azurerm_resource_group.main.name
  location                = var.location
  application_insights_id = azurerm_application_insights.main.id
  key_vault_id            = azurerm_key_vault.main.id
  storage_account_id      = azurerm_storage_account.ml.id
  tags                    = local.tags

  # This is the Azure ML setting specifically intended for regulated data.
  # It was absent, which is difficult to justify given the HIPAA framing.
  high_business_impact = true

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_machine_learning_compute_cluster" "gpu_spot" {
  name                          = "gpu-spot-cluster"
  machine_learning_workspace_id = azurerm_machine_learning_workspace.main.id
  vm_priority                   = "LowPriority"
  vm_size                       = local.ml_vm_sku

  scale_settings {
    min_node_count                       = 0
    max_node_count                       = 2
    scale_down_nodes_after_idle_duration = "PT10M"
  }

  identity {
    type = "SystemAssigned"
  }
}

# ── APIM — AI gateway ─────────────────────────────────────────────────────────

resource "azurerm_api_management" "main" {
  name                = "apim-${local.prefix}-${random_id.suffix.hex}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  publisher_name      = "SOC-AI Team"
  publisher_email     = var.alert_email
  sku_name            = "Developer_1"
  tags                = local.tags

  # Required for the article's "gateway retrieves secrets from Key Vault via
  # Managed Identity" claim. It was missing entirely.
  identity {
    type = "SystemAssigned"
  }
}

# The policy XML references {{tier1-...}} named values that were never
# created, so it could not be applied. These three make it resolvable.
resource "azurerm_api_management_named_value" "tier1_backend" {
  name                = "tier1-mistral-container-app-url"
  resource_group_name = azurerm_resource_group.main.name
  api_management_name = azurerm_api_management.main.name
  display_name        = "tier1-mistral-container-app-url"
  value               = "https://${azurerm_container_app.mistral_tier1.ingress[0].fqdn}"
}

resource "azurerm_api_management_named_value" "tier2_backend" {
  name                = "tier2-rag-azure-ml-endpoint-url"
  resource_group_name = azurerm_resource_group.main.name
  api_management_name = azurerm_api_management.main.name
  display_name        = "tier2-rag-azure-ml-endpoint-url"
  value               = "https://placeholder.invalid"
}

resource "azurerm_api_management_named_value" "tier3_backend" {
  name                = "tier3-hunt-azure-ml-batch-url"
  resource_group_name = azurerm_resource_group.main.name
  api_management_name = azurerm_api_management.main.name
  display_name        = "tier3-hunt-azure-ml-batch-url"
  value               = "https://placeholder.invalid"
}

resource "azurerm_api_management_named_value" "tenant_id" {
  name                = "aad-tenant-id"
  resource_group_name = azurerm_resource_group.main.name
  api_management_name = azurerm_api_management.main.name
  display_name        = "aad-tenant-id"
  value               = data.azurerm_client_config.current.tenant_id
}

# ── Audit logging — HIPAA 164.312(b) ─────────────────────────────────────────
# There were no diagnostic settings anywhere in the committed repo, so there
# was no audit trail on the gateway that enforces the compliance controls.

resource "azurerm_monitor_diagnostic_setting" "apim" {
  name                       = "diag-apim"
  target_resource_id         = azurerm_api_management.main.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category = "GatewayLogs"
  }

  metric {
    category = "AllMetrics"
  }
}

resource "azurerm_monitor_diagnostic_setting" "key_vault" {
  name                       = "diag-kv"
  target_resource_id         = azurerm_key_vault.main.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category = "AuditEvent"
  }

  metric {
    category = "AllMetrics"
  }
}

# ── Budget circuit breaker — fires at 80% actual, 100% forecast ─────────────

resource "azurerm_consumption_budget_resource_group" "soc" {
  name              = "budget-soc-${var.env}"
  resource_group_id = azurerm_resource_group.main.id
  amount            = var.asset_count < 100 ? 800 : 2000
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = [var.alert_email]
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = [var.alert_email]
  }
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "apim_gateway_url" {
  value = azurerm_api_management.main.gateway_url
}

output "ml_workspace_name" {
  value = azurerm_machine_learning_workspace.main.name
}

output "key_vault_uri" {
  value = azurerm_key_vault.main.vault_uri
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.main.id
}

# FIXED: was `{ value = ..., sensitive = true }` on one line.
output "aks_kube_config" {
  value     = azurerm_kubernetes_cluster.wazuh.kube_config_raw
  sensitive = true
}
