provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      app         = "cloud-pricing-app"
      environment = var.environment
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  env        = var.environment
  region     = var.aws_region
  prefix     = "cloud-pricing-app"
}
