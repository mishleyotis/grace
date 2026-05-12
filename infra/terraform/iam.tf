# Service accounts ----------------------------------------------------------

resource "google_service_account" "runtime" {
  account_id   = "grace-mcp-runtime"
  display_name = "Grace MCP runtime service account"
  description  = "Runs all 4 Cloud Run services; reads Secret Manager + Google Workspace APIs"
}

resource "google_service_account" "deployer" {
  account_id   = "grace-mcp-deployer"
  display_name = "Grace MCP deployer (GitHub Actions via WIF)"
  description  = "Used by GHA to push images and deploy Cloud Run services"
}

# Runtime SA permissions ---------------------------------------------------

resource "google_project_iam_member" "runtime_secret_accessor" {
  project = var.gcp_project
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# Deployer SA permissions --------------------------------------------------

resource "google_project_iam_member" "deployer_run_admin" {
  project = var.gcp_project
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_project_iam_member" "deployer_ar_writer" {
  project = var.gcp_project
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_act_as_runtime" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

# Workload Identity Federation for GitHub Actions --------------------------

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "grace-mcp-gh"
  display_name              = "Grace MCP GitHub Actions"
  description               = "WIF pool for GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub OIDC provider"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  attribute_condition = "attribute.repository == \"${var.github_repo}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "gha_can_impersonate_deployer" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}
