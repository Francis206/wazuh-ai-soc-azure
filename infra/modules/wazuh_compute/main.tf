resource "azurerm_public_ip" "wazuh" {
  name                = "pip-wazuh-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = var.tags
}

resource "azurerm_network_interface" "wazuh" {
  name                = "nic-wazuh-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = var.subnet_id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.wazuh.id
  }
}

# Wazuh manager/indexer/dashboard run as the docker-compose stack in
# docker-compose.yml, bootstrapped via cloud-init so the VM is
# self-configuring on first boot (clones this repo, runs docker compose up).
resource "azurerm_linux_virtual_machine" "wazuh" {
  name                = "vm-wazuh-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  size                = var.vm_size
  admin_username      = var.admin_username
  network_interface_ids = [azurerm_network_interface.wazuh.id]
  tags                = var.tags

  admin_ssh_key {
    username   = var.admin_username
    public_key = var.ssh_public_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = 128
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {
    repo_url = var.repo_url
  }))
}
