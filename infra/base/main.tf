# Long-lived resources for one environment (018-app-cloud-deployment, FR-032, FR-056;
# research.md R1). Applied once by the owner with administrator credentials; "down" never
# touches this stack.

# --- Account-wide items, looked up only (FR-056) ----------------------------------------------
# A missing item fails the plan in its lookup, before anything is created, and the provider's
# error names it. docs/deployment.md has a check command for each one.

data "aws_iam_openid_connect_provider" "github" {
  url = var.github_oidc_provider_url
}

data "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name
}

data "aws_s3_bucket" "data" {
  bucket = var.data_bucket_name
}

data "aws_iam_policy" "data_read" {
  name = var.data_read_policy_name
}

# --- Backups and the operation lock (FR-025, FR-030) -----------------------------------------

resource "aws_s3_bucket" "backups" {
  bucket        = "${local.prefix}-backups-${local.env}-${var.backup_bucket_suffix}"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket                  = aws_s3_bucket.backups.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "backups" {
  bucket = aws_s3_bucket.backups.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id
  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

# --- Logs and alerts (FR-043, FR-044) --------------------------------------------------------

resource "aws_cloudwatch_log_group" "app" {
  name              = "/${local.prefix}/${local.env}"
  retention_in_days = var.log_retention_days
}

resource "aws_sns_topic" "alerts" {
  name = "${local.prefix}-alerts-${local.env}"
}

resource "aws_sns_topic_subscription" "alert_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# --- Allowlist (FR-036, research.md R12) -----------------------------------------------------
# Seeded once; `deploy/app allow` owns the value afterwards. "none" means nobody is allowed.

resource "aws_ssm_parameter" "allowlist" {
  name  = "/${local.prefix}/${local.env}/allowlist"
  type  = "StringList"
  value = length(var.initial_allowlist) > 0 ? join(",", var.initial_allowlist) : "none"

  lifecycle {
    ignore_changes = [value]
  }
}
