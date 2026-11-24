variable "project_id" {
  type        = string
  description = "The Google Cloud Project ID (e.g., spry-levko-2026)"
  default     = "spry-levko-2026"
}

variable "region" {
  type        = string
  description = "Google Cloud region for resources"
  default     = "us-central1"
}

variable "project_name" {
  type        = string
  description = "Prefix for resource naming"
  default     = "spry"
}

variable "db_tier" {
  type        = string
  description = "Machine tier for Cloud SQL PostgreSQL instance"
  default     = "db-f1-micro"
}

variable "db_name" {
  type        = string
  description = "Name of the PostgreSQL database"
  default     = "meetings"
}

variable "db_user" {
  type        = string
  description = "Database username for application access"
  default     = "spry_app"
}

variable "container_image" {
  type        = string
  description = "Container image URL to deploy to Cloud Run"
  default     = "us-central1-docker.pkg.dev/spry-levko-2026/spry-repo/spry-backend:latest"
}
