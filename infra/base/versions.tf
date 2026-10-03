terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # State lives in the account's shared state bucket under app/<env>/ (FR-056):
  #   tofu init -backend-config=../envs/<env>.backend.hcl -backend-config="key=app/<env>/base.tfstate"
  backend "s3" {}
}
