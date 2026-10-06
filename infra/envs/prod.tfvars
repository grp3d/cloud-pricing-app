# Non-secret settings for prod (018-app-cloud-deployment; contracts/configuration.md). Read by
# both stacks. Secrets (alert_email) are TF_VAR_* environment variables, never committed. No
# account IDs and no personal IP addresses belong in this file.

environment = "prod"
aws_region  = "us-east-1"

# Account-wide items created by cloud-pricing-data-retrieval (FR-056). Referenced, never changed.
state_bucket_name     = "cloud-pricing-shared-tfstate-g08a9i" # same as bucket in prod.backend.hcl
data_bucket_name      = "cloud-pricing-data-prod-g08a9i"
data_read_policy_name = "cloud-pricing-data-read-prod"

# This repository on GitHub (public IDs: api.github.com/repos/grp3d/cloud-pricing-app).
github_repository = "grp3d/cloud-pricing-app"
github_owner_id   = "5554338"
github_repo_id    = "1378579975"

# base stack
log_retention_days   = 14
backup_bucket_suffix = "g08a9i"

# instance stack
instance_type   = "t4g.small"
root_volume_gib = 20
# Fill with `deploy/app ami-latest --env prod` (Canonical Ubuntu 24.04 arm64), then commit.
# `deploy/app up` refuses to run while this is the placeholder.
ami_id = "ami-0bec8cef5313300ad"
