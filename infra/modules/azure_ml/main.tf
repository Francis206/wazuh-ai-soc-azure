resource "random_id" "suffix" {
  byte_length = 3
}

resource "azurerm_application_insights" "this" {
  name                = "appi-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  application_type    = "web"
  tags                = var.tags
}

resource "azurerm_machine_learning_workspace" "this" {
  name                    = "mlw-${var.name_prefix}"
  location                = var.location
  resource_group_name     = var.resource_group_name
  application_insights_id = azurerm_application_insights.this.id
  key_vault_id            = var.key_vault_id
  storage_account_id      = var.storage_account_id
  identity {
    type = "SystemAssigned"
  }
  tags = var.tags
}

# GPU cluster used both for fine-tuning jobs (ml-training.yml) and, when the
# tuned adapter is promoted, for hosting the online inference endpoint.
# min_nodes defaults to 0 so idle time costs nothing between training runs.
resource "azurerm_machine_learning_compute_cluster" "gpu" {
  name                          = "gpu-cluster"
  location                      = var.location
  vm_priority                   = "Dedicated"
  vm_size                       = var.compute_vm_size
  machine_learning_workspace_id = azurerm_machine_learning_workspace.this.id

  scale_settings {
    min_node_count                       = var.compute_min_nodes
    max_node_count                       = var.compute_max_nodes
    scale_down_nodes_after_idle_duration = "PT15M"
  }

  identity {
    type = "SystemAssigned"
  }
}
