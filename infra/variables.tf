variable "azure_subscription_id" {
  description = "Azure subscription to deploy into"
  type        = string
}

variable "environment" {
  description = "Deployment environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

variable "project_name" {
  description = "Short project name used as a resource-naming prefix"
  type        = string
  default     = "soc-ai"
}

variable "wazuh_vm_size" {
  description = "VM size for the Wazuh manager/indexer/dashboard host"
  type        = string
  default     = "Standard_D4s_v5"
}

variable "wazuh_admin_username" {
  description = "Admin username for the Wazuh VM"
  type        = string
  default     = "socadmin"
}

variable "wazuh_ssh_public_key" {
  description = "SSH public key for the Wazuh VM admin user"
  type        = string
}

variable "aml_compute_min_nodes" {
  description = "Minimum node count for the Azure ML GPU training/inference compute cluster"
  type        = number
  default     = 0
}

variable "aml_compute_max_nodes" {
  description = "Maximum node count for the Azure ML GPU training/inference compute cluster"
  type        = number
  default     = 2
}

variable "aml_compute_vm_size" {
  description = "VM size for the Azure ML compute cluster (GPU SKU for fine-tuning)"
  type        = string
  default     = "Standard_NC6s_v3"
}

variable "tags" {
  description = "Common resource tags"
  type        = map(string)
  default = {
    project = "ai-augmented-soc"
    managed_by = "terraform"
  }
}
