output "cloud_run_url" {
  description = "Public HTTPS URL of the Spry Cloud Run backend API"
  value       = google_cloud_run_v2_service.api.uri
}

output "artifact_registry_repository" {
  description = "Artifact Registry Docker repository URL"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}"
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL instance connection name for Cloud Run volume integration"
  value       = google_sql_database_instance.db.connection_name
}

output "database_name" {
  description = "Name of the PostgreSQL database"
  value       = google_sql_database.database.name
}

output "database_user" {
  description = "Username for the PostgreSQL database"
  value       = google_sql_user.db_user.name
}

output "service_account_email" {
  description = "Email address of the dedicated Cloud Run runtime service account"
  value       = google_service_account.api_sa.email
}
