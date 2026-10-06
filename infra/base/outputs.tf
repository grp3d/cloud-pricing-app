# Read by deploy/app (`tofu output -json`) and by the instance stack (terraform_remote_state).

output "role_arns" {
  description = "Store these as the GitHub secrets AWS_ROLE_{PLAN,RELEASE,DEPLOY}_<ENV> (FR-050)."
  value       = { for k, r in aws_iam_role.gha : k => r.arn }
}

output "gha_trust_subjects" {
  description = "Compare with the oidc-subject workflow's output before the first deploy (FR-051)."
  value       = local.gha_subjects
}

output "backup_bucket" {
  value = aws_s3_bucket.backups.bucket
}

output "alert_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "log_group" {
  value = aws_cloudwatch_log_group.app.name
}

output "repository_urls" {
  value = { for k, r in aws_ecr_repository.app : k => r.repository_url }
}

output "repository_names" {
  value = { for k, r in aws_ecr_repository.app : k => r.name }
}

output "instance_profile_name" {
  value = aws_iam_instance_profile.instance.name
}

output "allowlist_parameter" {
  value = aws_ssm_parameter.allowlist.name
}

output "data_bucket_name" {
  value = data.aws_s3_bucket.data.bucket
}

output "environment" {
  value = local.env
}
