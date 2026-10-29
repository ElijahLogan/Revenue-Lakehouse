output "landing_volume_path" {
  description = "Set this as the LANDING_VOLUME secret in GitHub."
  value       = "/Volumes/${local.catalog}/raw/${databricks_volume.landing.name}"
}

