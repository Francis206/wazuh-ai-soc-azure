variable "name_prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "vm_size" {
  type = string
}

variable "admin_username" {
  type = string
}

variable "ssh_public_key" {
  type = string
}

variable "repo_url" {
  description = "Git URL cloud-init clones to bootstrap the Wazuh docker-compose stack"
  type        = string
  default     = "https://github.com/francis206/wazuh_azure_ml_mml.git"
}

variable "tags" {
  type = map(string)
}
