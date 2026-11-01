variable "catalog_name" {
  description = "Unity Catalog catalog to hold every layer."
  type        = string
  default     = "revenue"
}

variable "create_catalog" {
  description = "Create the catalog. Set false to reuse an existing catalog (e.g. the workspace default)."
  type        = bool
  default     = false
}

variable "analyst_group" {
  description = "Principal granted read access to gold only. Free Edition can't create account-level groups, so this uses the built-in 'account users' group."
  type        = string
  default     = "account users"
}

variable "create_analyst_group" {
  description = "Unity Catalog grants need an account-level group, which Free Edition can't create."
  type        = bool
  default     = false
}

