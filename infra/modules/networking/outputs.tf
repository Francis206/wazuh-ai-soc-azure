output "vnet_id" {
  value = azurerm_virtual_network.this.id
}

output "wazuh_subnet_id" {
  value = azurerm_subnet.wazuh.id
}

output "aml_subnet_id" {
  value = azurerm_subnet.aml.id
}
