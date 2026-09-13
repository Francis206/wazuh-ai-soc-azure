locals {
  name_prefix = "${var.project_name}-${var.environment}"
  tags        = merge(var.tags, { environment = var.environment })
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.name_prefix}"
  location = var.location
  tags     = local.tags
}

module "networking" {
  source = "./modules/networking"

  name_prefix         = local.name_prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

module "key_vault" {
  source = "./modules/key_vault"

  name_prefix          = local.name_prefix
  location             = var.location
  resource_group_name  = azurerm_resource_group.this.name
  azure_tenant_id      = data.azurerm_client_config.current.tenant_id
  tags                 = local.tags
}

module "storage" {
  source = "./modules/storage"

  name_prefix         = local.name_prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

module "wazuh_compute" {
  source = "./modules/wazuh_compute"

  name_prefix         = local.name_prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  subnet_id           = module.networking.wazuh_subnet_id
  vm_size             = var.wazuh_vm_size
  admin_username      = var.wazuh_admin_username
  ssh_public_key      = var.wazuh_ssh_public_key
  tags                = local.tags
}

module "azure_ml" {
  source = "./modules/azure_ml"

  name_prefix          = local.name_prefix
  location             = var.location
  resource_group_name  = azurerm_resource_group.this.name
  storage_account_id   = module.storage.storage_account_id
  key_vault_id         = module.key_vault.key_vault_id
  compute_min_nodes    = var.aml_compute_min_nodes
  compute_max_nodes    = var.aml_compute_max_nodes
  compute_vm_size      = var.aml_compute_vm_size
  tags                 = local.tags
}

data "azurerm_client_config" "current" {}
