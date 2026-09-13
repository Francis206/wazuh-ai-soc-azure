variable "name_prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "storage_account_id" {
  type = string
}

variable "key_vault_id" {
  type = string
}

variable "compute_min_nodes" {
  type = number
}

variable "compute_max_nodes" {
  type = number
}

variable "compute_vm_size" {
  type = string
}

variable "tags" {
  type = map(string)
}
