# The app's single instance (018-app-cloud-deployment, FR-019, FR-032, FR-038; research.md R3–R4).
# Everything on it is disposable: state lives in backups, the TLS root and secrets in SSM.

locals {
  registry_host = split("/", local.base.repository_urls.backend)[0]
  host_dir      = "${path.module}/../../deploy/host"
  units = {
    for name in ["app-backup.service", "app-backup.timer", "app-uptime.service", "app-uptime.timer"] :
    name => filebase64("${local.host_dir}/${name}")
  }
  # Settings for every backend-image service (contracts/configuration.md). No secret values:
  # cloud-init appends PUBLIC_ADDRESS and the generated database password at boot.
  env_lines = [
    "BACKEND_IMAGE=${local.base.repository_urls.backend}@${var.backend_digest}",
    "WEB_IMAGE=${local.base.repository_urls.web}@${var.web_digest}",
    "APP_RELEASE=${var.release}",
    "APP_ENVIRONMENT=${local.env}",
    "PRICING_DATA_URI=s3://${local.base.data_bucket_name}",
    "BACKUP_URI=s3://${local.base.backup_bucket}/${local.env}/db/",
    "ALERT_TOPIC_ARN=${local.base.alert_topic_arn}",
    "OWNER_PASSWORD_PARAMETER=/${local.prefix}/${local.env}/owner-password",
    "LOG_GROUP=${local.base.log_group}",
    "AWS_REGION=${var.aws_region}",
    "AWS_DEFAULT_REGION=${var.aws_region}",
    "DB_INIT_ARGS=${var.db_init_args}",
  ]
  user_data = templatefile("${local.host_dir}/cloud-init.yaml.tftpl", {
    registry_host = local.registry_host
    compose_b64   = filebase64("${path.module}/../../compose.yaml")
    env_lines     = local.env_lines
    units         = local.units
  })
}

resource "aws_instance" "app" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.app.id]
  iam_instance_profile        = local.base.instance_profile_name
  associate_public_ip_address = true
  user_data_base64            = base64gzip(local.user_data)
  user_data_replace_on_change = true

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
    # The containers (one hop further) use the instance role through IMDS.
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gib
    encrypted             = true
    delete_on_termination = true
  }

  tags = {
    Name    = "${local.prefix}-${local.env}"
    release = var.release
  }
}
