variable "name_prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "azure_tenant_id" {
  type = string
}

variable "tags" {
  type = map(string)
}
