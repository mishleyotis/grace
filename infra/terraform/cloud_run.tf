locals {
  registry_path = "${var.gcp_region}-docker.pkg.dev/${var.gcp_project}/${google_artifact_registry_repository.mcp.repository_id}"
}

resource "google_cloud_run_v2_service" "site_mirror" {
  name     = "grace-site-mirror"
  location = var.gcp_region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime.email

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = "${local.registry_path}/grace-site-mirror:${var.image_tag}"

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "GCP_PROJECT"
        value = var.gcp_project
      }

      env {
        name = "MCP_BEARER_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["grace-mcp-bearer-token"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "APPS_SCRIPT_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["grace-apps-script-url"].secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [
    google_project_iam_member.runtime_secret_accessor,
    google_secret_manager_secret_iam_member.runtime_can_read,
  ]
}

resource "google_cloud_run_v2_service" "sheets" {
  name     = "grace-sheets"
  location = var.gcp_region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime.email
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = "${local.registry_path}/grace-sheets:${var.image_tag}"
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "GCP_PROJECT"
        value = var.gcp_project
      }
      env {
        name = "MCP_BEARER_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["grace-mcp-bearer-token"].secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [
    google_project_iam_member.runtime_secret_accessor,
    google_secret_manager_secret_iam_member.runtime_can_read,
  ]
}

resource "google_cloud_run_v2_service" "slack" {
  name     = "grace-slack"
  location = var.gcp_region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime.email
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = "${local.registry_path}/grace-slack:${var.image_tag}"
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "GCP_PROJECT"
        value = var.gcp_project
      }
      env {
        name = "MCP_BEARER_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["grace-mcp-bearer-token"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "SLACK_BOT_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["grace-slack-bot-token"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "AUTHORITATIVE_SLACK_USER_IDS"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["grace-authoritative-slack-user-ids"].secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [
    google_project_iam_member.runtime_secret_accessor,
    google_secret_manager_secret_iam_member.runtime_can_read,
  ]
}

resource "google_cloud_run_v2_service" "orchestrator" {
  name     = "grace-orchestrator"
  location = var.gcp_region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime.email
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = "${local.registry_path}/grace-orchestrator:${var.image_tag}"
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "GCP_PROJECT"
        value = var.gcp_project
      }
      env {
        name = "MCP_BEARER_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["grace-mcp-bearer-token"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "SITE_MIRROR_URL"
        value = google_cloud_run_v2_service.site_mirror.uri
      }
      env {
        name  = "SHEETS_URL"
        value = google_cloud_run_v2_service.sheets.uri
      }
      env {
        name  = "SLACK_URL"
        value = google_cloud_run_v2_service.slack.uri
      }
    }
  }

  depends_on = [
    google_cloud_run_v2_service.site_mirror,
    google_cloud_run_v2_service.sheets,
    google_cloud_run_v2_service.slack,
  ]
}

# Public ingress at the GCP layer; auth is enforced at the app layer.
resource "google_cloud_run_v2_service_iam_member" "site_mirror_invoker" {
  name     = google_cloud_run_v2_service.site_mirror.name
  location = var.gcp_region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "sheets_invoker" {
  name     = google_cloud_run_v2_service.sheets.name
  location = var.gcp_region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "slack_invoker" {
  name     = google_cloud_run_v2_service.slack.name
  location = var.gcp_region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "orchestrator_invoker" {
  name     = google_cloud_run_v2_service.orchestrator.name
  location = var.gcp_region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
