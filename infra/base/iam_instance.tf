# The instance role (018-app-cloud-deployment, FR-042; contracts/infrastructure.md). In the base
# stack, so the deploy role needs no IAM writes, only iam:PassRole on this one role.

locals {
  repository_arns = [for r in aws_ecr_repository.app : r.arn]

  instance_statements = [
    {
      Sid      = "BackupObjects"
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
      Resource = ["${aws_s3_bucket.backups.arn}/${local.env}/db/*"]
    },
    {
      Sid       = "BackupListing"
      Effect    = "Allow"
      Action    = ["s3:ListBucket"]
      Resource  = [aws_s3_bucket.backups.arn]
      Condition = { StringLike = { "s3:prefix" = ["${local.env}/db/", "${local.env}/db/*"] } }
    },
    {
      Sid      = "OwnParameters"
      Effect   = "Allow"
      Action   = ["ssm:GetParameter", "ssm:GetParameters"]
      Resource = ["arn:aws:ssm:${local.region}:${local.account_id}:parameter/${local.prefix}/${local.env}/*"]
    },
    {
      Sid       = "DecryptOwnParametersViaSsm"
      Effect    = "Allow"
      Action    = ["kms:Decrypt"]
      Resource  = ["*"]
      Condition = { StringEquals = { "kms:ViaService" = "ssm.${local.region}.amazonaws.com" } }
    },
    {
      Sid      = "Alerts"
      Effect   = "Allow"
      Action   = ["sns:Publish"]
      Resource = [aws_sns_topic.alerts.arn]
    },
    {
      Sid      = "Logs"
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = ["${aws_cloudwatch_log_group.app.arn}:log-stream:*"]
    },
    {
      Sid      = "RegistryLogin"
      Effect   = "Allow"
      Action   = ["ecr:GetAuthorizationToken"]
      Resource = ["*"]
    },
    {
      Sid      = "RegistryPull"
      Effect   = "Allow"
      Action   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
      Resource = local.repository_arns
    },
  ]
}

resource "aws_iam_role" "instance" {
  name = "${local.prefix}-instance-${local.env}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "instance" {
  name   = "${local.prefix}-instance-${local.env}"
  role   = aws_iam_role.instance.id
  policy = jsonencode({ Version = "2012-10-17", Statement = local.instance_statements })
}

resource "aws_iam_role_policy_attachment" "instance_ssm_core" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# The pipeline's read-only data policy (FR-042): manifests and Parquet only.
resource "aws_iam_role_policy_attachment" "instance_data_read" {
  role       = aws_iam_role.instance.name
  policy_arn = data.aws_iam_policy.data_read.arn
}

resource "aws_iam_instance_profile" "instance" {
  name = "${local.prefix}-instance-${local.env}"
  role = aws_iam_role.instance.name
}
