output "site_mirror_url" {
  value = google_cloud_run_v2_service.site_mirror.uri
}

output "sheets_url" {
  value = google_cloud_run_v2_service.sheets.uri
}

output "slack_url" {
  value = google_cloud_run_v2_service.slack.uri
}

output "orchestrator_url" {
  value = google_cloud_run_v2_service.orchestrator.uri
}

output "runtime_sa_email" {
  value = google_service_account.runtime.email
}

output "deployer_sa_email" {
  value = google_service_account.deployer.email
}

output "wif_provider" {
  value = "projects/${var.gcp_project}/locations/global/workloadIdentityPools/${google_iam_workload_identity_pool.github.workload_identity_pool_id}/providers/${google_iam_workload_identity_pool_provider.github.workload_identity_pool_provider_id}"
}

output "artifact_registry_repo" {
  value = "${var.gcp_region}-docker.pkg.dev/${var.gcp_project}/${google_artifact_registry_repository.mcp.repository_id}"
}
