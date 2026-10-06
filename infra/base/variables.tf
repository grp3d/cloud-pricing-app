# Inputs for the long-lived base stack (018-app-cloud-deployment; contracts/infrastructure.md,
# contracts/configuration.md). Non-secret values come from infra/envs/<env>.tfvars;
# alert_email is passed as TF_VAR_alert_email and never committed.

variable "environment" {
  description = "Environment name."
  type        = string
  validation {
    condition     = contains(["dev", "qa", "prod"], var.environment)
    error_message = "environment must be dev, qa or prod."
  }
}

variable "aws_region" {
  description = "Region for every resource. Passed explicitly, never read from local AWS config (FR-048)."
  type        = string
  validation {
    condition     = can(regex("^[a-z]{2}(-[a-z]+)+-[0-9]$", var.aws_region))
    error_message = "aws_region must look like us-east-1."
  }
}

# --- Account-wide items this stack refers to but never creates (FR-056) ---------------------

variable "state_bucket_name" {
  description = "The account's shared OpenTofu state bucket (created by cloud-pricing-data-retrieval)."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.state_bucket_name)) && !can(regex("[0-9]{12}", var.state_bucket_name))
    error_message = "state_bucket_name must be a valid bucket name without an AWS account ID."
  }
}

variable "github_oidc_provider_url" {
  description = "URL of the account's existing GitHub Actions OIDC provider."
  type        = string
  default     = "https://token.actions.githubusercontent.com"
  validation {
    condition     = startswith(var.github_oidc_provider_url, "https://")
    error_message = "github_oidc_provider_url must be an https:// URL."
  }
}

variable "data_bucket_name" {
  description = "The pipeline's pricing data bucket for this environment."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.data_bucket_name))
    error_message = "data_bucket_name must be a valid bucket name."
  }
}

variable "data_read_policy_name" {
  description = "The pipeline's read-only data policy for this environment (cloud-pricing-data-read-<env>)."
  type        = string
  validation {
    condition     = can(regex("^[A-Za-z0-9+=,.@_-]+$", var.data_read_policy_name))
    error_message = "data_read_policy_name must be an IAM policy name."
  }
}

# --- This repository on GitHub ---------------------------------------------------------------

variable "github_repository" {
  description = "owner/name of this repository."
  type        = string
  default     = "grp3d/cloud-pricing-app"
  validation {
    condition     = can(regex("^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$", var.github_repository))
    error_message = "github_repository must be owner/name."
  }
}

variable "github_owner_id" {
  description = "Numeric GitHub ID of the owner (public: https://api.github.com/users/<owner>)."
  type        = string
  validation {
    condition     = can(regex("^[0-9]+$", var.github_owner_id))
    error_message = "github_owner_id must be numeric."
  }
}

variable "github_repo_id" {
  description = "Numeric GitHub ID of the repository (public: https://api.github.com/repos/<owner>/<name>)."
  type        = string
  validation {
    condition     = can(regex("^[0-9]+$", var.github_repo_id))
    error_message = "github_repo_id must be numeric."
  }
}

# --- Settings ---------------------------------------------------------------------------------

variable "alert_email" {
  description = "Where alerts go (backup failures, uptime, the address notice). Supplied as TF_VAR_alert_email."
  type        = string
  sensitive   = true
  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be an email address."
  }
}

variable "log_retention_days" {
  description = "Retention of the application log group (FR-043)."
  type        = number
  default     = 14
  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90], var.log_retention_days)
    error_message = "log_retention_days must be a CloudWatch retention value up to 90."
  }
}

variable "backup_bucket_suffix" {
  description = "A short suffix that makes the backup bucket name globally unique. Never an account ID."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9]{4,12}$", var.backup_bucket_suffix)) && !can(regex("^[0-9]{12}$", var.backup_bucket_suffix))
    error_message = "backup_bucket_suffix must be 4-12 lowercase letters or digits."
  }
}

variable "initial_allowlist" {
  description = "Addresses to seed the allowlist with on first apply (/32 or /128). Later changes use `deploy/app allow`."
  type        = list(string)
  default     = []
  validation {
    condition = alltrue([
      for a in var.initial_allowlist : can(cidrhost(a, 0)) && (endswith(a, "/32") || endswith(a, "/128"))
    ])
    error_message = "initial_allowlist entries must be single addresses written as /32 or /128."
  }
}

# Unused by this stack; declared so one <env>.tfvars serves both stacks without warnings.
variable "ami_id" {
  type    = string
  default = null
}
variable "instance_type" {
  type    = string
  default = null
}
variable "root_volume_gib" {
  type    = number
  default = null
}
