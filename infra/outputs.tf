output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "wazuh_public_ip" {
  value = module.wazuh_compute.public_ip_address
}

output "azure_ml_workspace_name" {
  value = module.azure_ml.workspace_name
}

output "storage_account_name" {
  value = module.storage.storage_account_name
}

output "key_vault_uri" {
  value = module.key_vault.key_vault_uri
}
