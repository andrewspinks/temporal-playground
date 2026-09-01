terraform {
  required_providers {
    temporalcloud = {
      source = "temporalio/temporalcloud"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "temporalcloud" {
  api_key            = var.temporal_api_key
  allowed_account_id = var.temporal_account_id
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  # Refuse to apply if the resolved credentials point at a different account.
  allowed_account_ids = [var.aws_account_id]
}

resource "temporalcloud_namespace_export_sink" "sink-export-sink" {
  namespace = local.temporal_namespace
  sink_name = var.sink_name
  # enabled   = false

  s3 = {
    aws_account_id = var.aws_account_id
    bucket_name    = var.s3_bucket_name
    region         = var.aws_region
    role_name      = aws_iam_role.temporal_cloud_export.name
  }
}

locals {
  temporal_namespace = "${var.temporal_namespace_name}.${var.temporal_account_id}"
  s3_bucket_arn      = "arn:aws:s3:::${var.s3_bucket_name}"

  # Temporal Cloud's export accounts, per the CF AssumeRolePolicyDocument.
  temporal_export_principals = [
    "arn:aws:iam::902542641901:role/closed-workflow-export",
    "arn:aws:iam::160190466495:role/closed-workflow-export",
    "arn:aws:iam::819232936619:role/closed-workflow-export",
    "arn:aws:iam::829909441867:role/closed-workflow-export",
    "arn:aws:iam::354116250941:role/closed-workflow-export",
  ]
}

data "aws_iam_policy_document" "temporal_cloud_export_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = local.temporal_export_principals
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [var.assume_role_external_id]
    }
  }
}

resource "aws_iam_role" "temporal_cloud_export" {
  name                 = var.role_name
  description          = "The role Temporal Cloud uses to export workflow history to customer's S3 bucket"
  max_session_duration = 3600
  assume_role_policy   = data.aws_iam_policy_document.temporal_cloud_export_assume_role.json
}

data "aws_iam_policy_document" "temporal_cloud_s3_permissions" {
  statement {
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = [
      local.s3_bucket_arn,
      "${local.s3_bucket_arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "temporal_cloud_s3_permissions" {
  name   = "Temporal-Cloud-S3-Permissions"
  role   = aws_iam_role.temporal_cloud_export.id
  policy = data.aws_iam_policy_document.temporal_cloud_s3_permissions.json
}

data "aws_iam_policy_document" "temporal_cloud_kms_permissions" {
  statement {
    effect    = "Allow"
    actions   = ["kms:GenerateDataKey"]
    resources = [var.kms_arn]
  }
}

resource "aws_iam_role_policy" "temporal_cloud_kms_permissions" {
  count = var.kms_arn == "" ? 0 : 1

  name   = "Temporal-Cloud-KMS-Permissions"
  role   = aws_iam_role.temporal_cloud_export.id
  policy = data.aws_iam_policy_document.temporal_cloud_kms_permissions.json
}
