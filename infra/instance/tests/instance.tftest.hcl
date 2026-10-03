# The instance stack's guarantees (018-app-cloud-deployment, FR-032, FR-035, FR-039, FR-052;
# contracts/infrastructure.md "Tests that must exist" 1–3). Offline: mocked AWS provider, and the
# base stack's outputs and the allowlist parameter overridden.
#   tofu init -backend=false && tofu test

mock_provider "aws" {
  mock_resource "aws_vpc" {
    defaults = { id = "vpc-0123456789abcdef0" }
  }
  mock_resource "aws_security_group" {
    defaults = { id = "sg-0123456789abcdef0" }
  }
}

override_data {
  target = data.terraform_remote_state.base
  values = {
    outputs = {
      allowlist_parameter   = "/cloud-pricing-app/prod/allowlist"
      backup_bucket         = "cloud-pricing-app-backups-prod-test01"
      alert_topic_arn       = "arn:aws:sns:us-east-1:123456789012:cloud-pricing-app-alerts-prod"
      log_group             = "/cloud-pricing-app/prod"
      instance_profile_name = "cloud-pricing-app-instance-prod"
      data_bucket_name      = "cloud-pricing-data-prod-test01"
      repository_urls = {
        backend = "123456789012.dkr.ecr.us-east-1.amazonaws.com/cloud-pricing-app-backend-prod"
        web     = "123456789012.dkr.ecr.us-east-1.amazonaws.com/cloud-pricing-app-web-prod"
      }
    }
  }
}

override_data {
  target = data.aws_ssm_parameter.allowlist
  values = { insecure_value = "203.0.113.5/32,2001:db8::1/128" }
}

variables {
  environment       = "prod"
  aws_region        = "us-east-1"
  state_bucket_name = "cloud-pricing-shared-tfstate-test01"
  ami_id            = "ami-0123456789abcdef0"
  instance_type     = "t4g.small"
  root_volume_gib   = 20
  release           = "v1.2.3"
  backend_digest    = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
  web_digest        = "sha256:2222222222222222222222222222222222222222222222222222222222222222"
  db_init_args      = ""
}

# Test 1 ("nothing long-lived, no IAM writes") and "no SSH key pair" (key_name is computed, so
# unknown at plan) can't be asserted here; the CI infra job greps infra/instance/*.tf (T088).

run "ingress_is_443_from_each_allowlist_entry_only" {
  command = plan

  assert {
    condition     = length(aws_vpc_security_group_ingress_rule.https) == 2
    error_message = "One ingress rule per allowlisted address."
  }
  assert {
    condition = alltrue([
      for r in aws_vpc_security_group_ingress_rule.https :
      r.from_port == 443 && r.to_port == 443 && r.ip_protocol == "tcp"
    ])
    error_message = "Ingress is port 443/tcp only: no 22, no 80 (FR-035, FR-039)."
  }
  assert {
    condition     = toset([for r in aws_vpc_security_group_ingress_rule.https : coalesce(r.cidr_ipv4, r.cidr_ipv6)]) == toset(["203.0.113.5/32", "2001:db8::1/128"])
    error_message = "Ingress comes exactly from the allowlist entries."
  }
  assert {
    condition = alltrue([
      for r in aws_vpc_security_group_ingress_rule.https :
      r.cidr_ipv4 != "0.0.0.0/0" && r.cidr_ipv6 != "::/0"
    ])
    error_message = "Never open to the whole internet."
  }
}

run "placeholder_allowlist_means_no_ingress" {
  command = plan

  override_data {
    target = data.aws_ssm_parameter.allowlist
    values = { insecure_value = "none" }
  }

  assert {
    condition     = length(aws_vpc_security_group_ingress_rule.https) == 0
    error_message = "The placeholder 'none' opens nothing."
  }
}

run "instance_is_hardened_and_disposable" {
  command = plan

  assert {
    condition     = one(aws_instance.app.metadata_options).http_tokens == "required"
    error_message = "IMDSv2 is required (test 3)."
  }
  assert {
    condition = alltrue([
      one(aws_instance.app.root_block_device).encrypted,
      one(aws_instance.app.root_block_device).delete_on_termination,
    ])
    error_message = "The root volume is encrypted and deleted with the instance (FR-032)."
  }
  assert {
    condition     = aws_instance.app.associate_public_ip_address == true
    error_message = "The instance gets a fresh public IP each bring-up, no Elastic IP (FR-038)."
  }
  assert {
    condition     = aws_instance.app.user_data_replace_on_change == true
    error_message = "A user-data change (release, AMI, restore choice) replaces the instance."
  }
  assert {
    condition     = aws_instance.app.iam_instance_profile == "cloud-pricing-app-instance-prod"
    error_message = "The instance uses the base stack's instance profile."
  }
  assert {
    condition     = aws_instance.app.tags["release"] == "v1.2.3"
    error_message = "The instance is tagged with its release."
  }
}

run "user_data_holds_digests_and_no_secrets" {
  command = plan

  assert {
    condition     = strcontains(local.user_data, "cloud-pricing-app-backend-prod@sha256:1111111111111111111111111111111111111111111111111111111111111111") && strcontains(local.user_data, "cloud-pricing-app-web-prod@sha256:2222222222222222222222222222222222222222222222222222222222222222")
    error_message = "Images are deployed by digest."
  }
  assert {
    condition     = !strcontains(lower(local.user_data), "password=") || strcontains(local.user_data, "POSTGRES_PASSWORD=$")
    error_message = "No password value is in user-data; the database password is generated at boot."
  }
  assert {
    condition     = !strcontains(local.user_data, "BEGIN") && !strcontains(local.user_data, "PRIVATE KEY")
    error_message = "No key material in user-data."
  }
  assert {
    condition     = strcontains(local.user_data, "PRICING_DATA_URI=s3://cloud-pricing-data-prod-test01")
    error_message = "The instance reads the pipeline's bucket."
  }
  assert {
    condition     = strcontains(local.user_data, "BACKUP_URI=s3://cloud-pricing-app-backups-prod-test01/prod/db/")
    error_message = "Backups go to the env's prefix."
  }
}

run "restore_choice_reaches_db_init" {
  command = plan

  variables {
    db_init_args = "--backup 20261001T000000Z-scheduled-v1.0.0"
  }

  assert {
    condition     = strcontains(local.user_data, "DB_INIT_ARGS=--backup 20261001T000000Z-scheduled-v1.0.0")
    error_message = "--backup is passed to db-init (FR-023)."
  }
}

run "environment_names_are_isolated" {
  command = plan

  # T069 (FR-034).
  variables {
    environment = "qa"
  }

  assert {
    condition = alltrue([
      aws_security_group.app.name == "cloud-pricing-app-qa",
      aws_instance.app.tags["Name"] == "cloud-pricing-app-qa",
      aws_vpc.app.tags["Name"] == "cloud-pricing-app-qa",
      strcontains(local.user_data, "APP_ENVIRONMENT=qa"),
      strcontains(local.user_data, "/qa/db/"),
      strcontains(local.user_data, "/cloud-pricing-app/qa/owner-password"),
    ])
    error_message = "A qa stack names everything qa and uses qa's backups and parameters."
  }
}

run "rejects_bad_inputs" {
  command = plan
  variables {
    backend_digest = "latest"
  }
  expect_failures = [var.backend_digest]
}
