# Inputs for the disposable instance stack (018-app-cloud-deployment; contracts/configuration.md).
# Environment-wide values come from infra/envs/<env>.tfvars; the release, digests and restore
# choice come from deploy/app (FR-057).

variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "qa", "prod"], var.environment)
    error_message = "environment must be dev, qa or prod."
  }
}

variable "aws_region" {
  type = string
}

variable "state_bucket_name" {
  description = "The shared state bucket holding the base stack's state."
  type        = string
}

variable "ami_id" {
  description = "Canonical Ubuntu 24.04 arm64 AMI, pinned per env (deploy/app ami-latest)."
  type        = string
  validation {
    condition     = can(regex("^ami-[0-9a-f]{8,17}$", var.ami_id))
    error_message = "ami_id must be an AMI ID; fill it with deploy/app ami-latest."
  }
}

variable "instance_type" {
  type    = string
  default = "t4g.small"
}

variable "root_volume_gib" {
  type    = number
  default = 20
  validation {
    condition     = var.root_volume_gib >= 16 && var.root_volume_gib <= 100
    error_message = "root_volume_gib must be between 16 and 100."
  }
}

variable "release" {
  description = "The v* release deployed."
  type        = string
  validation {
    condition     = can(regex("^v[0-9]+\\.[0-9]+\\.[0-9]+$", var.release))
    error_message = "release must look like v1.2.3."
  }
}

variable "backend_digest" {
  type = string
  validation {
    condition     = can(regex("^sha256:[0-9a-f]{64}$", var.backend_digest))
    error_message = "backend_digest must be an image digest (sha256:…)."
  }
}

variable "web_digest" {
  type = string
  validation {
    condition     = can(regex("^sha256:[0-9a-f]{64}$", var.web_digest))
    error_message = "web_digest must be an image digest (sha256:…)."
  }
}

variable "db_init_args" {
  description = "Extra db-init arguments: empty, or --backup <id> (FR-023)."
  type        = string
  default     = ""
  validation {
    condition     = var.db_init_args == "" || can(regex("^--backup [0-9]{8}T[0-9]{6}Z-[a-z]+-[A-Za-z0-9.]+$", var.db_init_args))
    error_message = "db_init_args must be empty or --backup <backup id>."
  }
}

# Base-stack inputs that share <env>.tfvars; unused here.
variable "data_bucket_name" {
  type    = string
  default = null
}
variable "data_read_policy_name" {
  type    = string
  default = null
}
variable "github_repository" {
  type    = string
  default = null
}
variable "github_owner_id" {
  type    = string
  default = null
}
variable "github_repo_id" {
  type    = string
  default = null
}
variable "log_retention_days" {
  type    = number
  default = null
}
variable "backup_bucket_suffix" {
  type    = string
  default = null
}
