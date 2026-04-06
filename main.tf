terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 3.90" }
  }
  backend "azurerm" {
    resource_group_name  = "rg-soc-tfstate"
    storage_account_name = "socaitfstate"
    container_name       = "tfstate"
    key                  = "soc-ai.terraform.tfstate"
  }
}

provider "azurerm" { features {} }

variable "location"    { default = "eastus2" }
variable "env"         { default = "prod" }
variable "asset_count" { default = 50 }

locals {
  prefix   = "socai-${var.env}"
  tags     = { environment = var.env, compliance = "hipaa-nist", owner = "soc-team" }
  aks_vm_sku = var.asset_count < 100 ? "Standard_DS2_v2" : "Standard_DS4_v2"
  ml_vm_sku  = var.asset_count < 100 ? "Standard_NC4as_T4_v3" : "Standard_NC8as_T4_v3"
}

data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.prefix}"
  location = var.location
  tags     = local.tags
}

# ── Key Vault — PHI encryption keys and all secrets ──────────────────────────
resource "azurerm_key_vault" "main" {
  name                        = "kv-${local.prefix}"
  resource_group_name         = azurerm_resource_group.main.name
  location                    = var.location
  sku_name                    = "standard"
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  purge_protection_enabled    = true
  soft_delete_retention_days  = 90
  tags                        = local.tags
  network_acls {
    bypass         = "AzureServices"
    default_action = "Deny"
  }
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
  identity { type = "SystemAssigned" }
  oms_agent { log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id }
  network_profile {
    network_plugin    = "azure"
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

resource "azurerm_container_app" "mistral_tier1" {
  name                         = "ca-mistral-t1-${local.prefix}"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.inference.id
  revision_mode                = "Multiple"   # blue/green
  tags                         = local.tags
  template {
    container {
      name   = "ollama-mistral"
      image  = "ollama/ollama:latest"
      cpu    = 2.0
      memory = "4Gi"
      env { name = "OLLAMA_MODELS", value = "/mnt/models" }
    }
    min_replicas = 1
    max_replicas = var.asset_count < 100 ? 3 : 6
  }
  ingress {
    external_enabled = false
    target_port      = 11434
    traffic_weight { percentage = 100, latest_revision = true }
  }
}

# ── Azure ML — training workspace ────────────────────────────────────────────
resource "azurerm_storage_account" "ml" {
  name                     = "stsocml${var.env}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
  tags                     = local.tags
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
  identity { type = "SystemAssigned" }
}

# Spot GPU cluster — scales to 0 when idle, ~60% cheaper than on-demand
resource "azurerm_machine_learning_compute_cluster" "gpu_spot" {
  name                          = "gpu-spot-cluster"
  machine_learning_workspace_id = azurerm_machine_learning_workspace.main.id
  vm_priority                   = "LowPriority"
  vm_size                       = local.ml_vm_sku
  # location is inherited from the ML workspace — do not set explicitly
  scale_settings {
    min_node_count                       = 0
    max_node_count                       = 2
    scale_down_nodes_after_idle_duration = "PT10M"
  }
  identity { type = "SystemAssigned" }
}

# ── APIM — AI gateway ─────────────────────────────────────────────────────────
resource "azurerm_api_management" "main" {
  name                = "apim-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  publisher_name      = "SOC-AI Team"
  publisher_email     = "soc@yourorg.com"
  sku_name            = "Developer_1"   # upgrade to Standard_1 for production HA
  tags                = local.tags
}

# ── Budget circuit breaker — fires at 80% actual, 100% forecast ─────────────
resource "azurerm_consumption_budget_resource_group" "soc" {
  name              = "budget-soc-${var.env}"
  resource_group_id = azurerm_resource_group.main.id
  amount            = var.asset_count < 100 ? 800 : 2000
  time_grain        = "Monthly"
  # start_date must be the first day of a current or future month (Azure requirement)
  time_period { start_date = formatdate("YYYY-MM-01'T'00:00:00Z", timestamp()) }
  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = ["soc@yourorg.com"]
  }
  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = ["soc@yourorg.com"]
  }
}

output "apim_gateway_url"  { value = azurerm_api_management.main.gateway_url }
output "ml_workspace_name" { value = azurerm_machine_learning_workspace.main.name }
output "key_vault_uri"     { value = azurerm_key_vault.main.vault_uri }
output "aks_kube_config"   { value = azurerm_kubernetes_cluster.wazuh.kube_config_raw, sensitive = true }
