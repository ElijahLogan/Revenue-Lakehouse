terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.60"
    }
  }
}

# Authenticates with DATABRICKS_HOST and DATABRICKS_TOKEN from the environment.
provider "databricks" {}

# ---------------------------------------------------------------------------
# Catalog and medallion schemas
# ---------------------------------------------------------------------------

resource "databricks_catalog" "revenue" {
  count   = var.create_catalog ? 1 : 0
  name    = var.catalog_name
  comment = "Revenue lakehouse: Salesforce + Stripe, medallion architecture."
}

locals {
  catalog = var.create_catalog ? databricks_catalog.revenue[0].name : var.catalog_name
  schemas = {
    raw          = "Landing volume for raw extracts and pipeline state."
    bronze       = "Raw records loaded as-is by Auto Loader."
    silver       = "Typed, validated, deduplicated source tables."
    intermediate = "dbt intermediate models (entity resolution, matching)."
    gold         = "Business-ready marts. The only layer analysts can read."
  }
}

resource "databricks_schema" "layer" {
  for_each     = local.schemas
  catalog_name = local.catalog
  name         = each.key
  comment      = each.value
}

resource "databricks_volume" "landing" {
  catalog_name = local.catalog
  schema_name  = databricks_schema.layer["raw"].name
  name         = "landing"
  volume_type  = "MANAGED"
  comment      = "Raw NDJSON written by the GitHub Actions extractors."
}

# ---------------------------------------------------------------------------
# Access control: analysts see gold only. Raw, bronze and silver stay private.
# ---------------------------------------------------------------------------

resource "databricks_group" "analysts" {
  count        = var.create_analyst_group ? 1 : 0
  display_name = var.analyst_group
}

resource "databricks_grants" "catalog" {
  catalog = local.catalog
  grant {
    principal  = var.analyst_group
    privileges = ["USE_CATALOG"]
  }
  depends_on = [databricks_group.analysts]
}

resource "databricks_grants" "gold" {
  schema = "${local.catalog}.${databricks_schema.layer["gold"].name}"
  grant {
    principal  = var.analyst_group
    privileges = ["USE_SCHEMA", "SELECT"]
  }
  depends_on = [databricks_group.analysts]
}

