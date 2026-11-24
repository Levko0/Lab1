# Dedicated runtime service account for Cloud Run API (Least Privilege)
resource "google_service_account" "api_sa" {
  depends_on = [google_project_service.enabled_services]

  project      = var.project_id
  account_id   = "${var.project_name}-api-sa"
  display_name = "Service Account for Spry Cloud Run API"
}

# Grant Cloud SQL Client permission to Cloud Run service account
resource "google_project_iam_member" "sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api_sa.email}"
}

# Grant Secret Accessor on the database password to Cloud Run service account
resource "google_secret_manager_secret_iam_member" "secret_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.db_password.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api_sa.email}"
}

# Cloud Run v2 API Service
resource "google_cloud_run_v2_service" "api" {
  depends_on = [
    google_project_service.enabled_services,
    google_project_iam_member.sql_client,
    google_secret_manager_secret_version.db_password_version
  ]

  project  = var.project_id
  name     = "${var.project_name}-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.api_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.db.connection_name]
      }
    }

    containers {
      image = var.container_image

      ports {
        container_port = 8080
      }

      env {
        name  = "PORT"
        value = "8080"
      }

      env {
        name  = "APP_TIMEZONE"
        value = "Europe/Kyiv"
      }

      env {
        name  = "CORS_ORIGINS"
        value = "*"
      }

      env {
        name  = "RUN_MIGRATIONS_ON_START"
        value = "true"
      }

      env {
        name  = "DB_SOCKET_DIR"
        value = "/cloudsql"
      }

      env {
        name  = "INSTANCE_CONNECTION_NAME"
        value = google_sql_database_instance.db.connection_name
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }
  }
}

# Allow unauthenticated invocation for public API access
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
