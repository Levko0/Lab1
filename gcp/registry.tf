resource "google_artifact_registry_repository" "repo" {
  depends_on = [google_project_service.enabled_services]

  project       = var.project_id
  location      = var.region
  repository_id = "${var.project_name}-repo"
  description   = "Docker container repository for Spry backend API images"
  format        = "DOCKER"
}
