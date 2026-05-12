resource "google_logging_metric" "auth_failures" {
  name        = "grace_mcp_auth_failures"
  description = "Bearer-auth failures across all 4 MCP services"

  filter = <<-EOT
    resource.type="cloud_run_revision"
    jsonPayload.message="invalid_bearer_token"
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_logging_metric" "tracker_write_failures" {
  name        = "grace_mcp_tracker_write_failures"
  description = "Onboarding Tracker write failures"

  filter = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="grace-sheets"
    jsonPayload.message=~"tracker.*failed"
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_monitoring_notification_channel" "email" {
  count        = var.alert_email == "" ? 0 : 1
  display_name = "Grace MCP alerts"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

resource "google_monitoring_alert_policy" "five_xx_rate" {
  display_name = "Grace MCP 5xx rate elevated"
  combiner     = "OR"

  conditions {
    display_name = "5xx > 0 for 5 minutes"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\" metric.label.\"response_code_class\"=\"5xx\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = var.alert_email == "" ? [] : [google_monitoring_notification_channel.email[0].name]
}

resource "google_monitoring_alert_policy" "auth_failures" {
  display_name = "Grace MCP bearer-auth failures elevated"
  combiner     = "OR"

  conditions {
    display_name = "Auth failures > 10/min for 5 minutes"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.auth_failures.name}\" resource.type=\"cloud_run_revision\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 10
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = var.alert_email == "" ? [] : [google_monitoring_notification_channel.email[0].name]
}

resource "google_monitoring_alert_policy" "tracker_writes" {
  display_name = "Grace MCP tracker write failures"
  combiner     = "OR"

  conditions {
    display_name = "Tracker write failure for 5 minutes"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.tracker_write_failures.name}\" resource.type=\"cloud_run_revision\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = var.alert_email == "" ? [] : [google_monitoring_notification_channel.email[0].name]
}
