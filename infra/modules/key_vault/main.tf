resource "random_id" "suffix" {
  byte_length = 3
}

resource "azurerm_key_vault" "this" {
  name                       = substr("kv-${replace(var.name_prefix, "-", "")}${random_id.suffix.hex}", 0, 24)
  location                   = var.location
  resource_group_name        = var.resource_group_name
  tenant_id                  = var.azure_tenant_id
  sku_name                   = "standard"
  purge_protection_enabled   = false
  soft_delete_retention_days = 7
  tags                       = var.tags
}
