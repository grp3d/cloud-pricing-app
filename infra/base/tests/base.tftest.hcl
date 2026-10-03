# The base stack's guarantees (018-app-cloud-deployment, FR-032, FR-049, FR-052;
# contracts/infrastructure.md "Tests that must exist" 4–6). Offline: mocked AWS provider.
#   tofu init -backend=false && tofu test

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_iam_openid_connect_provider" {
    defaults = { arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" }
  }
  mock_data "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::cloud-pricing-shared-tfstate-test01" }
  }
  mock_data "aws_iam_policy" {
    defaults = { arn = "arn:aws:iam::123456789012:policy/cloud-pricing-data-read-mock" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::cloud-pricing-app-backups-mock-test01" }
  }
  mock_resource "aws_ecr_repository" {
    defaults = { arn = "arn:aws:ecr:us-east-1:123456789012:repository/mock" }
  }
  mock_resource "aws_sns_topic" {
    defaults = { arn = "arn:aws:sns:us-east-1:123456789012:cloud-pricing-app-alerts-mock" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:us-east-1:123456789012:log-group:/cloud-pricing-app/mock" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/cloud-pricing-app-instance-mock" }
  }
}

variables {
  environment           = "prod"
  aws_region            = "us-east-1"
  state_bucket_name     = "cloud-pricing-shared-tfstate-test01"
  data_bucket_name      = "cloud-pricing-data-prod-test01"
  data_read_policy_name = "cloud-pricing-data-read-prod"
  github_owner_id       = "5554338"
  github_repo_id        = "1378579975"
  alert_email           = "owner@example.com"
  backup_bucket_suffix  = "test01"
}

# Test 4's "no aws_instance or aws_vpc in the base stack" is a resource-type check, which
# `tofu test` can't express; the CI infra job greps for it (T088).

run "exactly_three_ci_roles" {
  command = plan

  assert {
    condition     = toset(keys(aws_iam_role.gha)) == toset(["plan", "release", "deploy"])
    error_message = "Exactly three CI roles: plan, release, deploy (research.md R2)."
  }
}

run "backup_bucket_is_private_and_encrypted" {
  command = plan

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.backups.block_public_acls,
      aws_s3_bucket_public_access_block.backups.block_public_policy,
      aws_s3_bucket_public_access_block.backups.ignore_public_acls,
      aws_s3_bucket_public_access_block.backups.restrict_public_buckets,
    ])
    error_message = "The backup bucket must block all public access (FR-025)."
  }
  assert {
    condition     = one(one(aws_s3_bucket_server_side_encryption_configuration.backups.rule).apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    error_message = "The backup bucket must be encrypted at rest (FR-025)."
  }
  assert {
    condition     = aws_s3_bucket.backups.force_destroy == false
    error_message = "The backup bucket must never be force-destroyed (FR-032)."
  }
  assert {
    condition     = aws_s3_bucket.backups.bucket == "cloud-pricing-app-backups-prod-test01"
    error_message = "Backup bucket name follows cloud-pricing-app-backups-<env>-<suffix>."
  }
}

run "registries_are_immutable_and_kept" {
  command = plan

  assert {
    condition     = alltrue([for r in aws_ecr_repository.app : r.image_tag_mutability == "IMMUTABLE"])
    error_message = "Release images must be immutable (FR-018)."
  }
  assert {
    condition     = alltrue([for r in aws_ecr_repository.app : one(r.image_scanning_configuration).scan_on_push])
    error_message = "Both repositories scan on push."
  }
  assert {
    condition     = alltrue([for r in aws_ecr_repository.app : r.force_delete == false])
    error_message = "Repositories must not be force-deletable (FR-032)."
  }
  assert {
    condition     = toset([for r in aws_ecr_repository.app : r.name]) == toset(["cloud-pricing-app-backend-prod", "cloud-pricing-app-web-prod"])
    error_message = "Exactly the env's backend and web repositories."
  }
  assert {
    condition = alltrue([
      for p in aws_ecr_lifecycle_policy.app : (
        length(jsondecode(p.policy).rules) == 2 &&
        contains([for r in jsondecode(p.policy).rules : r.selection.countNumber], 5) &&
        contains([for r in jsondecode(p.policy).rules : r.selection.tagStatus], "untagged")
      )
    ])
    error_message = "Lifecycle: keep 5 tagged releases, expire untagged after 1 day."
  }
}

run "trust_subjects_are_exact" {
  command = plan

  # Test 5.
  assert {
    condition = output.gha_trust_subjects == {
      plan    = ["repo:grp3d@5554338/cloud-pricing-app@1378579975:pull_request:ref:refs/pull/*/merge"]
      release = ["repo:grp3d@5554338/cloud-pricing-app@1378579975:ref:refs/tags/v*"]
      deploy  = ["repo:grp3d@5554338/cloud-pricing-app@1378579975:environment:prod:ref:refs/heads/main"]
    }
    error_message = "Trust subjects must be exactly: PRs for plan, v* tags for release, the prod environment on main for deploy."
  }
  assert {
    condition = alltrue([
      for k, r in aws_iam_role.gha :
      jsondecode(r.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    ])
    error_message = "Every CI role checks the audience."
  }
  assert {
    condition     = toset([for r in aws_iam_role.gha : r.name]) == toset(["cloud-pricing-app-gha-plan-prod", "cloud-pricing-app-gha-release-prod", "cloud-pricing-app-gha-deploy-prod"])
    error_message = "Role names follow cloud-pricing-app-gha-<purpose>-<env>."
  }
}

run "release_role_only_pushes_two_repositories" {
  command = plan

  assert {
    condition = alltrue([
      for s in jsondecode(aws_iam_role_policy.gha["release"].policy).Statement :
      s.Resource == ["*"] ? s.Action == ["ecr:GetAuthorizationToken"] : alltrue([for r in s.Resource : startswith(r, "arn:aws:ecr:")])
    ])
    error_message = "The release role's only non-* resources are the env's ECR repositories (test 5)."
  }
  assert {
    condition = alltrue([
      for s in jsondecode(aws_iam_role_policy.gha["release"].policy).Statement :
      alltrue([for a in s.Action : startswith(a, "ecr:")])
    ])
    error_message = "The release role has ECR actions only."
  }
  assert {
    condition     = length(jsondecode(aws_iam_role_policy.gha["release"].policy).Statement[1].Resource) == 2
    error_message = "Exactly two repositories."
  }
}

run "deploy_wildcards_are_approved_or_tag_scoped" {
  command = plan

  # Test 6: every Resource "*" statement is a *-only action from the verified list, or is
  # limited by a tag or create-action condition.
  assert {
    condition = alltrue([
      for s in jsondecode(aws_iam_role_policy.gha["deploy"].policy).Statement :
      !contains(s.Resource, "*") || contains(["ReadOnlyDiscovery", "CommandResults"], s.Sid) || anytrue([
        for k in keys(try(s.Condition.StringEquals, {})) :
        startswith(k, "aws:RequestTag/") || startswith(k, "aws:ResourceTag/") || k == "ec2:CreateAction"
      ])
    ])
    error_message = "A deploy statement with Resource * is neither approved nor tag-scoped."
  }
  assert {
    condition = alltrue([
      for s in jsondecode(aws_iam_role_policy.gha["deploy"].policy).Statement :
      !contains(["ReadOnlyDiscovery", "CommandResults"], s.Sid) || alltrue([
        for a in s.Action : can(regex("^(ec2:Describe\\*|sts:GetCallerIdentity|ssm:GetCommandInvocation|ssm:ListCommandInvocations|ssm:DescribeInstanceInformation)$", a))
      ])
    ])
    error_message = "Approved wildcard statements hold only the verified *-only actions."
  }
  assert {
    condition = alltrue([
      for s in jsondecode(aws_iam_role_policy.gha["deploy"].policy).Statement :
      alltrue([for a in s.Action : !startswith(a, "iam:") || a == "iam:PassRole"])
    ])
    error_message = "The deploy role has no IAM write permissions, only PassRole (research.md R2)."
  }
  assert {
    condition = one([
      for s in jsondecode(aws_iam_role_policy.gha["deploy"].policy).Statement : s if s.Sid == "PassInstanceRole"
    ]).Condition.StringEquals["iam:PassedToService"] == "ec2.amazonaws.com"
    error_message = "PassRole is limited to EC2."
  }
  assert {
    condition = one([
      for s in jsondecode(aws_iam_role_policy.gha["deploy"].policy).Statement : s if s.Sid == "RunCommandOnTaggedInstance"
    ]).Condition.StringEquals["ssm:resourceTag/environment"] == "prod"
    error_message = "Run Command is limited to the env's tagged instance with ssm:resourceTag."
  }
  assert {
    condition = alltrue([
      for s in jsondecode(aws_iam_role_policy.gha["deploy"].policy).Statement :
      alltrue([for r in s.Resource : !strcontains(r, ":parameter/") || strcontains(r, "/cloud-pricing-app/prod/") || strcontains(r, "/aws/service/canonical/")])
    ])
    error_message = "Parameter access is limited to /cloud-pricing-app/<env>/ (and Canonical's public AMI ids)."
  }
}

run "plan_role_is_read_only" {
  command = plan

  assert {
    condition = alltrue([
      for s in jsondecode(aws_iam_role_policy.gha["plan"].policy).Statement :
      s.Sid == "StateLockFiles" || alltrue([
        for a in s.Action : can(regex("^(s3:GetObject|s3:ListBucket|ssm:GetParameters?|ecr:DescribeImages|ec2:Describe\\*|sts:GetCallerIdentity)$", a))
      ])
    ])
    error_message = "The plan role only reads (plus its own .tflock files)."
  }
  assert {
    condition = alltrue(flatten([
      for s in jsondecode(aws_iam_role_policy.gha["plan"].policy).Statement :
      [for r in s.Resource : endswith(r, ".tflock")] if s.Sid == "StateLockFiles"
    ]))
    error_message = "The plan role can write lock files only."
  }
}

run "instance_role_reaches_only_its_environment" {
  command = plan

  assert {
    condition = one([
      for s in jsondecode(aws_iam_role_policy.instance.policy).Statement : s if s.Sid == "BackupObjects"
    ]).Resource == ["arn:aws:s3:::cloud-pricing-app-backups-mock-test01/prod/db/*"]
    error_message = "The instance writes backups only under <env>/db/."
  }
  assert {
    condition     = aws_iam_role_policy_attachment.instance_data_read.policy_arn == "arn:aws:iam::123456789012:policy/cloud-pricing-data-read-mock"
    error_message = "The instance reads pricing data through the pipeline's read policy (FR-042)."
  }
  assert {
    condition     = aws_ssm_parameter.allowlist.value == "none" && aws_ssm_parameter.allowlist.type == "StringList"
    error_message = "With no initial entries, the allowlist is the placeholder none."
  }
}

run "environment_names_are_isolated" {
  command = plan

  # T069 (FR-034): a qa stack names only qa.
  variables {
    environment           = "qa"
    data_bucket_name      = "cloud-pricing-data-qa-test01"
    data_read_policy_name = "cloud-pricing-data-read-qa"
  }

  assert {
    condition = alltrue([
      for n in concat(
        [aws_s3_bucket.backups.bucket, aws_cloudwatch_log_group.app.name, aws_sns_topic.alerts.name,
         aws_ssm_parameter.allowlist.name, aws_iam_role.instance.name, aws_iam_instance_profile.instance.name],
        [for r in aws_ecr_repository.app : r.name],
        [for r in aws_iam_role.gha : r.name],
      ) : strcontains(n, "qa") && !strcontains(n, "prod")
    ])
    error_message = "Every qa resource name contains qa and never prod."
  }
  assert {
    condition     = output.gha_trust_subjects.deploy == ["repo:grp3d@5554338/cloud-pricing-app@1378579975:environment:qa:ref:refs/heads/main"]
    error_message = "The qa deploy role trusts only the qa GitHub environment."
  }
  assert {
    condition = alltrue([
      for s in jsondecode(aws_iam_role_policy.gha["deploy"].policy).Statement :
      alltrue([for r in s.Resource : !strcontains(r, "prod")])
    ])
    error_message = "The qa deploy role's resources never mention prod."
  }
  assert {
    condition     = one([for s in jsondecode(aws_iam_role_policy.gha["deploy"].policy).Statement : s if s.Sid == "State"]).Resource == ["arn:aws:s3:::cloud-pricing-shared-tfstate-test01/app/qa/*"]
    error_message = "The qa state prefix is app/qa/."
  }
}

run "rejects_account_id_in_bucket_suffix" {
  command = plan
  variables {
    backup_bucket_suffix = "123456789012"
  }
  expect_failures = [var.backup_bucket_suffix]
}
