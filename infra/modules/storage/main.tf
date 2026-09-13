resource "random_id" "suffix" {
  byte_length = 3
}

resource "azurerm_storage_account" "this" {
  name                     = substr("st${replace(var.name_prefix, "-", "")}${random_id.suffix.hex}", 0, 24)
  location                 = var.location
  resource_group_name      = var.resource_group_name
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
  tags                     = var.tags
}

# Holds fine-tuning datasets (ml/data) and trained adapters (ml/models)
# referenced as Azure ML data assets.
resource "azurerm_storage_container" "ml_data" {
  name                  = "ml-data"
  storage_account_name  = azurerm_storage_account.this.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "ml_models" {
  name                  = "ml-models"
  storage_account_name  = azurerm_storage_account.this.name
  container_access_type = "private"
}
