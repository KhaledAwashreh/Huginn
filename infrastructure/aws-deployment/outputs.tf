output "github_actions_variables" {
  description = "Set these GitHub repository or production environment variables after applying."
  value = {
    AWS_DEPLOY_ROLE_ARN  = aws_iam_role.github_deployment.arn
    AWS_REGION           = var.aws_region
    EC2_DEPLOY_TAG_VALUE = var.deployment_tag_value
  }
}

output "instance_profile_name" {
  description = "For an instance with no profile, select this name in EC2's Modify IAM role action once."
  value       = local.manage_profile ? aws_iam_instance_profile.ssm[0].name : data.aws_iam_instance_profile.existing[0].name
}

output "instance_profile_arn" {
  description = "Created or preserved profile; this module does not change EC2 profile associations."
  value       = local.manage_profile ? aws_iam_instance_profile.ssm[0].arn : data.aws_iam_instance_profile.existing[0].arn
}

output "instance_profile_attachment_required" {
  description = "True until the operator attaches the created SSM profile to the existing instance."
  value       = local.attached_profile == ""
}
