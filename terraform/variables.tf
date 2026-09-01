variable "temporal_api_key" {
  type      = string
  sensitive = true
}

variable "temporal_account_id" {
  type        = string
  description = "Temporal Cloud account ID; also the namespace suffix"
}

variable "temporal_namespace_name" {
  type        = string
  description = "Namespace name without the account suffix"
}

variable "sink_name" {
  type        = string
  description = "Name of the namespace export sink"
}

variable "aws_account_id" {
  type        = string
  description = "AWS account that owns the export bucket and the IAM role"

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "Must be a 12-digit AWS account ID."
  }
}

variable "aws_region" {
  type        = string
  description = "Region of the export bucket; also the AWS provider region"
  default     = "us-west-2"
}

variable "aws_profile" {
  type        = string
  description = "AWS shared-config profile to authenticate with; null falls back to the default credential chain (AWS_PROFILE, env vars, instance role)"
  default     = null
}

variable "s3_bucket_name" {
  type        = string
  description = "Export bucket name; the CF S3ARN parameter is derived from this"
}
variable "assume_role_external_id" {
  type        = string
  description = "The External ID provided by Temporal"

  validation {
    condition     = can(regex("^[a-zA-Z0-9_+=,.@-]*$", var.assume_role_external_id))
    error_message = "Must match [a-zA-Z0-9_+=,.@-]*."
  }

  validation {
    condition     = length(var.assume_role_external_id) >= 5 && length(var.assume_role_external_id) <= 45
    error_message = "Must be between 5 and 45 characters."
  }
}

variable "role_name" {
  type        = string
  description = "Name of the IAM role Temporal Cloud assumes"
}

variable "kms_arn" {
  type        = string
  description = "Optional KMS key ARN; when empty the KMS policy is not created"
  default     = ""
}
