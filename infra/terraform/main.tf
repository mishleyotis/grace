locals {
  services = ["site-mirror", "sheets", "slack", "orchestrator"]
}

resource "google_project_service" "required" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iamcredentials.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "sheets.googleapis.com",
    "drive.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "mcp" {
  location      = var.gcp_region
  repository_id = var.artifact_registry_repo
  format        = "DOCKER"
  description   = "Grace MCP service images"

  depends_on = [google_project_service.required]
}
