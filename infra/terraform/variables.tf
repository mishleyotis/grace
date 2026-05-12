variable "gcp_project" {
  type        = string
  description = "GCP project ID hosting all 4 MCP services."
}

variable "gcp_region" {
  type        = string
  description = "Cloud Run region."
  default     = "us-central1"
}

variable "artifact_registry_repo" {
  type        = string
  description = "Artifact Registry Docker repo name."
  default     = "grace-mcp"
}

variable "image_tag" {
  type        = string
  description = "Docker image tag (typically the git SHA)."
  default     = "latest"
}

variable "min_instances" {
  type        = number
  description = "Cloud Run min instances per service. 0 = cost-optimized, 1 = no cold starts."
  default     = 0
}

variable "max_instances" {
  type    = number
  default = 10
}

variable "alert_email" {
  type        = string
  description = "Email for Cloud Monitoring alerts. Empty = no notification channel."
  default     = ""
}

variable "github_repo" {
  type        = string
  description = "GitHub repo in 'owner/repo' form, used for the WIF principal binding."
  default     = "mishleyotis/grace"
}

variable "github_branch" {
  type        = string
  description = "Branch that may impersonate the deployer SA."
  default     = "main"
}
