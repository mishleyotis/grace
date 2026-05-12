locals {
  secret_names = [
    "grace-mcp-bearer-token",
    "grace-slack-bot-token",
    "grace-apps-script-url",
    "grace-authoritative-slack-user-ids",
  ]
}

resource "google_secret_manager_secret" "secrets" {
  for_each  = toset(local.secret_names)
  secret_id = each.value

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

# Each Cloud Run service needs read access to all 4 secrets. We grant at the
# project level via runtime_secret_accessor in iam.tf; per-secret bindings
# are optional but kept here for explicit auditability.
resource "google_secret_manager_secret_iam_member" "runtime_can_read" {
  for_each  = google_secret_manager_secret.secrets
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}
