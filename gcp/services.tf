# Enable required Google Cloud APIs for Spry
locals {
  services = [
    "run.googleapis.com",                 # Cloud Run Admin API
    "sqladmin.googleapis.com",            # Cloud SQL Admin API
    "artifactregistry.googleapis.com",    # Artifact Registry API
    "secretmanager.googleapis.com",       # Secret Manager API
    "iam.googleapis.com",                 # Identity and Access Management API
    "cloudresourcemanager.googleapis.com" # Resource Manager API
  ]
}

resource "google_project_service" "enabled_services" {
  for_each = toset(local.services)

  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}
