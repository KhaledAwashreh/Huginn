data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

# Lookup only: this configuration never owns or imports the EC2 instance.
data "aws_instance" "target" {
  instance_id = var.instance_id
}

locals {
  partition            = data.aws_partition.current.partition
  account_id           = data.aws_caller_identity.current.account_id
  managed_profile_name = "${var.name_prefix}-ssm"
  attached_profile     = data.aws_instance.target.iam_instance_profile == null ? "" : data.aws_instance.target.iam_instance_profile
  # Retain ownership after the operator attaches the profile we created.
  manage_profile = local.attached_profile == "" || local.attached_profile == local.managed_profile_name
  oidc_arn       = var.existing_oidc_provider_arn != null ? var.existing_oidc_provider_arn : aws_iam_openid_connect_provider.github[0].arn
}

resource "aws_ec2_tag" "deployment" {
  resource_id = data.aws_instance.target.id
  key         = "HuginnDeployment"
  value       = var.deployment_tag_value
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.existing_oidc_provider_arn == null ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role" "github_deployment" {
  name = "${var.name_prefix}-github"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:KhaledAwashreh@40263357/Huginn@1360631904:environment:production"
        }
      }
    }]
  })

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy" "github_deployment" {
  name = "${var.name_prefix}-run-command"
  role = aws_iam_role.github_deployment.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ssm:DescribeInstanceInformation",
          "ssm:GetCommandInvocation"
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = "ssm:SendCommand"
        Resource = "arn:${local.partition}:ssm:${var.aws_region}::document/AWS-RunShellScript"
      },
      {
        Effect   = "Allow"
        Action   = "ssm:SendCommand"
        Resource = "arn:${local.partition}:ec2:${var.aws_region}:${local.account_id}:instance/*"
        Condition = {
          StringEquals = { "ssm:resourceTag/HuginnDeployment" = var.deployment_tag_value }
        }
      }
    ]
  })
}

data "aws_iam_instance_profile" "existing" {
  count = local.manage_profile ? 0 : 1
  name  = local.attached_profile
}

resource "aws_iam_role" "ssm" {
  count = local.manage_profile ? 1 : 0

  name = local.managed_profile_name
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_instance_profile" "ssm" {
  count = local.manage_profile ? 1 : 0

  name = local.managed_profile_name
  role = aws_iam_role.ssm[0].name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = local.manage_profile ? aws_iam_role.ssm[0].name : data.aws_iam_instance_profile.existing[0].role_name
  policy_arn = "arn:${local.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
