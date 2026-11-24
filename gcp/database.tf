# Random strong password for database user
resource "random_password" "db_password" {
  length  = 24
  special = false
}

# Store database password securely in Google Cloud Secret Manager
resource "google_secret_manager_secret" "db_password" {
  depends_on = [google_project_service.enabled_services]

  project   = var.project_id
  secret_id = "${var.project_name}-db-password"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password_version" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db_password.result
}

# Cloud SQL PostgreSQL Instance (smallest shared-core tier: db-f1-micro, 10 GB SSD)
resource "google_sql_database_instance" "db" {
  depends_on = [google_project_service.enabled_services]

  project             = var.project_id
  name                = "${var.project_name}-postgres"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = false

  settings {
    tier              = var.db_tier
    disk_size         = 10
    disk_type         = "PD_SSD"
    availability_type = "ZONAL"

    ip_configuration {
      ipv4_enabled = true
    }

    backup_configuration {
      enabled    = false # disabled for lab cost optimization
      start_time = "03:00"
    }
  }
}

# Logical Database
resource "google_sql_database" "database" {
  project  = var.project_id
  name     = var.db_name
  instance = google_sql_database_instance.db.name
}

# Database User
resource "google_sql_user" "db_user" {
  project  = var.project_id
  name     = var.db_user
  instance = google_sql_database_instance.db.name
  password = random_password.db_password.result
}
