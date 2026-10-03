provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      app         = "cloud-pricing-app"
      environment = var.environment
    }
  }
}

# The long-lived base stack's outputs (FR-032): instance profile, backup bucket, registry, etc.
data "terraform_remote_state" "base" {
  backend = "s3"
  config = {
    bucket = var.state_bucket_name
    key    = "app/${var.environment}/base.tfstate"
    region = var.aws_region
  }
}

locals {
  env    = var.environment
  prefix = "cloud-pricing-app"
  base   = data.terraform_remote_state.base.outputs
}
