variable "instance_id" {
  description = "Existing EC2 instance ID in aws_region; the instance itself is never managed."
  type        = string

  validation {
    condition     = can(regex("^i-[0-9a-f]{8,17}$", var.instance_id))
    error_message = "Supply the existing EC2 instance ID, not its public IP."
  }
}

variable "aws_region" {
  description = "AWS region containing the existing instance."
  type        = string
  default     = "eu-north-1"
}

variable "deployment_tag_value" {
  description = "Value for the single HuginnDeployment tag used by the pipeline."
  type        = string
  default     = "huginn-production"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]{1,128}$", var.deployment_tag_value))
    error_message = "Use letters, digits, dots, underscores or hyphens for the deployment tag."
  }
}

variable "name_prefix" {
  description = "Stable namespace for this bootstrap's IAM resources; keep it after applying."
  type        = string
  default     = "huginn-deployment"

  validation {
    condition     = can(regex("^[A-Za-z0-9_-]{1,40}$", var.name_prefix))
    error_message = "The IAM namespace must be 1-40 letters, digits, underscores or hyphens."
  }
}

variable "existing_oidc_provider_arn" {
  description = "Existing account-wide GitHub OIDC provider ARN, or null to create it once."
  type        = string
  default     = null

  validation {
    condition     = var.existing_oidc_provider_arn == null || can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:oidc-provider/token\\.actions\\.githubusercontent\\.com$", var.existing_oidc_provider_arn))
    error_message = "Supply the existing GitHub OIDC provider ARN, or leave null to create it."
  }
}
