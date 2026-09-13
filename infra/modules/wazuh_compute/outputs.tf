output "public_ip_address" {
  value = azurerm_public_ip.wazuh.ip_address
}

output "vm_id" {
  value = azurerm_linux_virtual_machine.wazuh.id
}
