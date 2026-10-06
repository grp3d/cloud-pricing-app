# GitHub Actions roles for this environment (018-app-cloud-deployment, FR-049–FR-051;
# research.md R2, contracts/infrastructure.md "Verified action list").
#
# plan    — pull requests: read state, describe, read parameters (the PR preview).
# release — v* tags: push the env's two images, nothing else.
# deploy  — the <env> GitHub environment on main: the instance stack, SSM commands to the env's
#           tagged instance, the env's parameters, the operation lock.
#
# Policies are built with jsonencode from plain lists, so `tofu test` can check every statement.

locals {
  oidc_host = replace(var.github_oidc_provider_url, "https://", "")
  gh_owner  = split("/", var.github_repository)[0]
  gh_name   = split("/", var.github_repository)[1]
  # The immutable subject format (repositories created after 2026-07-15), with the repo's
  # subject template set to ["repo", "context", "ref"] (docs/deployment.md, one-time setup).
  gh_sub_repo = "repo:${local.gh_owner}@${var.github_owner_id}/${local.gh_name}@${var.github_repo_id}"

  gha_subjects = {
    plan    = ["${local.gh_sub_repo}:pull_request:ref:refs/pull/*/merge"]
    release = ["${local.gh_sub_repo}:ref:refs/tags/v*"]
    deploy  = ["${local.gh_sub_repo}:environment:${local.env}:ref:refs/heads/main"]
  }

  state_arn      = data.aws_s3_bucket.state.arn
  state_objects  = "${local.state_arn}/app/${local.env}/*"
  instance_role  = aws_iam_role.instance.arn
  own_parameters = "arn:aws:ssm:${local.region}:${local.account_id}:parameter/${local.prefix}/${local.env}/*"
  canonical_amis = "arn:aws:ssm:${local.region}::parameter/aws/service/canonical/*"
  tag_request = {
    "aws:RequestTag/environment" = local.env
    "aws:RequestTag/app"         = local.prefix
  }
  tag_resource = {
    "aws:ResourceTag/environment" = local.env
    "aws:ResourceTag/app"         = local.prefix
  }

  discovery_statement = {
    Sid      = "ReadOnlyDiscovery"
    Effect   = "Allow"
    Action   = ["ec2:Describe*", "sts:GetCallerIdentity"]
    Resource = ["*"]
  }

  plan_statements = [
    {
      Sid      = "StateRead"
      Effect   = "Allow"
      Action   = ["s3:GetObject"]
      Resource = [local.state_objects]
    },
    {
      Sid      = "StateLockFiles"
      Effect   = "Allow"
      Action   = ["s3:PutObject", "s3:DeleteObject"]
      Resource = ["${local.state_arn}/app/${local.env}/*.tflock"]
    },
    {
      Sid      = "StateList"
      Effect   = "Allow"
      Action   = ["s3:ListBucket"]
      Resource = [local.state_arn]
    },
    {
      Sid      = "Parameters"
      Effect   = "Allow"
      Action   = ["ssm:GetParameter", "ssm:GetParameters"]
      Resource = [local.own_parameters, local.canonical_amis]
    },
    {
      Sid      = "ResolveRelease"
      Effect   = "Allow"
      Action   = ["ecr:DescribeImages"]
      Resource = local.repository_arns
    },
    local.discovery_statement,
  ]

  release_statements = [
    {
      Sid      = "RegistryLogin"
      Effect   = "Allow"
      Action   = ["ecr:GetAuthorizationToken"]
      Resource = ["*"]
    },
    {
      Sid    = "PushAndCheck"
      Effect = "Allow"
      Action = [
        "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:DescribeImages", "ecr:BatchGetImage",
      ]
      Resource = local.repository_arns
    },
  ]

  deploy_statements = [
    {
      Sid      = "State"
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
      Resource = [local.state_objects]
    },
    {
      Sid      = "StateList"
      Effect   = "Allow"
      Action   = ["s3:ListBucket"]
      Resource = [local.state_arn]
    },
    {
      Sid    = "CreateTaggedNetwork"
      Effect = "Allow"
      Action = [
        "ec2:CreateVpc", "ec2:CreateSubnet", "ec2:CreateInternetGateway", "ec2:CreateRouteTable",
        "ec2:CreateSecurityGroup",
      ]
      Resource  = ["*"]
      Condition = { StringEquals = local.tag_request }
    },
    {
      Sid      = "TagOnCreate"
      Effect   = "Allow"
      Action   = ["ec2:CreateTags"]
      Resource = ["*"]
      Condition = {
        StringEquals = {
          "ec2:CreateAction" = [
            "CreateVpc", "CreateSubnet", "CreateInternetGateway", "CreateRouteTable",
            "CreateSecurityGroup", "AuthorizeSecurityGroupIngress", "AuthorizeSecurityGroupEgress",
            "RunInstances",
          ]
        }
      }
    },
    {
      Sid       = "ManageTaggedResources"
      Effect    = "Allow"
      Action    = ["ec2:*"]
      Resource  = ["*"]
      Condition = { StringEquals = local.tag_resource }
    },
    {
      Sid       = "CreateTaggedSecurityGroupRules"
      Effect    = "Allow"
      Action    = ["ec2:AuthorizeSecurityGroupIngress", "ec2:AuthorizeSecurityGroupEgress"]
      Resource  = ["arn:aws:ec2:${local.region}:${local.account_id}:security-group-rule/*"]
      Condition = { StringEquals = local.tag_request }
    },
    {
      Sid       = "LaunchTaggedInstance"
      Effect    = "Allow"
      Action    = ["ec2:RunInstances"]
      Resource  = ["arn:aws:ec2:${local.region}:${local.account_id}:instance/*"]
      Condition = { StringEquals = local.tag_request }
    },
    {
      # Created only together with the tagged instance above, in a tagged subnet.
      Sid    = "LaunchInstanceParts"
      Effect = "Allow"
      Action = ["ec2:RunInstances"]
      Resource = [
        "arn:aws:ec2:${local.region}:${local.account_id}:network-interface/*",
        "arn:aws:ec2:${local.region}:${local.account_id}:volume/*",
      ]
    },
    {
      # Public images from AWS and its verified publishers (Canonical's Ubuntu images carry the
      # owner alias "amazon", which is what ec2:Owner evaluates — not Canonical's account ID).
      # Community, Marketplace and account-owned images are refused. The exact AMI is pinned in
      # <env>.tfvars, so an AMI update needs no base-stack apply.
      Sid       = "LaunchFromVerifiedPublicImage"
      Effect    = "Allow"
      Action    = ["ec2:RunInstances"]
      Resource  = ["arn:aws:ec2:${local.region}::image/*"]
      Condition = { StringEquals = { "ec2:Owner" = "amazon", "ec2:Public" = "true" } }
    },
    {
      Sid       = "PassInstanceRole"
      Effect    = "Allow"
      Action    = ["iam:PassRole"]
      Resource  = [local.instance_role]
      Condition = { StringEquals = { "iam:PassedToService" = "ec2.amazonaws.com" } }
    },
    {
      Sid      = "RunShellScriptDocument"
      Effect   = "Allow"
      Action   = ["ssm:SendCommand"]
      Resource = ["arn:aws:ssm:${local.region}::document/AWS-RunShellScript"]
    },
    {
      # Run Command checks ssm:resourceTag/<key> on the instance, not aws:ResourceTag.
      Sid      = "RunCommandOnTaggedInstance"
      Effect   = "Allow"
      Action   = ["ssm:SendCommand"]
      Resource = ["arn:aws:ec2:${local.region}:${local.account_id}:instance/*"]
      Condition = {
        StringEquals = {
          "ssm:resourceTag/environment" = local.env
          "ssm:resourceTag/app"         = local.prefix
        }
      }
    },
    {
      Sid      = "CommandResults"
      Effect   = "Allow"
      Action   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations", "ssm:DescribeInstanceInformation"]
      Resource = ["*"]
    },
    {
      Sid      = "OwnParameters"
      Effect   = "Allow"
      Action   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:PutParameter"]
      Resource = [local.own_parameters]
    },
    {
      Sid      = "CanonicalAmiParameter"
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = [local.canonical_amis]
    },
    {
      Sid      = "OperationLock"
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
      Resource = ["${aws_s3_bucket.backups.arn}/locks/${local.env}.json"]
    },
    {
      Sid       = "BackupListing"
      Effect    = "Allow"
      Action    = ["s3:ListBucket"]
      Resource  = [aws_s3_bucket.backups.arn]
      Condition = { StringLike = { "s3:prefix" = ["${local.env}/db/", "${local.env}/db/*"] } }
    },
    {
      Sid      = "Notify"
      Effect   = "Allow"
      Action   = ["sns:Publish"]
      Resource = [aws_sns_topic.alerts.arn]
    },
    {
      Sid      = "ResolveRelease"
      Effect   = "Allow"
      Action   = ["ecr:DescribeImages"]
      Resource = local.repository_arns
    },
    local.discovery_statement,
  ]

  ci_roles = {
    plan    = local.plan_statements
    release = local.release_statements
    deploy  = local.deploy_statements
  }
}

resource "aws_iam_role" "gha" {
  for_each = local.ci_roles
  name     = "${local.prefix}-gha-${each.key}-${local.env}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = { "${local.oidc_host}:aud" = "sts.amazonaws.com" }
        StringLike   = { "${local.oidc_host}:sub" = local.gha_subjects[each.key] }
      }
    }]
  })
}

resource "aws_iam_role_policy" "gha" {
  for_each = local.ci_roles
  name     = "${local.prefix}-gha-${each.key}-${local.env}"
  role     = aws_iam_role.gha[each.key].id
  policy   = jsonencode({ Version = "2012-10-17", Statement = each.value })
}
