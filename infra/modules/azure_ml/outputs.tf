output "workspace_name" {
  value = azurerm_machine_learning_workspace.this.name
}

output "workspace_id" {
  value = azurerm_machine_learning_workspace.this.id
}

output "compute_cluster_name" {
  value = azurerm_machine_learning_compute_cluster.gpu.name
}
