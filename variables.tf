variable "catalog_name" {
  description = "Unity Catalog catalog to hold every layer."
  type        = string
  default     = "revenue"
}

variable "create_catalog" {
  description = "Create the catalog. Set false to reuse an existing catalog (e.g. the workspace default)."
  type        = bool
  default     = true
}

variable "analyst_group" {
  description = "Group granted read access to the gold schema only."
  type        = string
  default     = "revenue_analysts"
}

variable "create_analyst_group" {
  description = "Create the analyst group in the workspace."
  type        = bool
  default     = true
}

