mock_provider "aws" {
  override_during = plan

  mock_resource "aws_iam_openid_connect_provider" {
    defaults = {
      arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
    }
  }
}

variables {
  instance_id = "i-0123456789abcdef0"
}

override_data {
  target = data.aws_caller_identity.current
  values = {
    account_id = "123456789012"
  }
}

override_data {
  target = data.aws_partition.current
  values = {
    partition = "aws"
  }
}

run "new_instance_profile_bootstrap" {
  command = plan

  override_data {
    target = data.aws_instance.target
    values = {
      id                   = "i-0123456789abcdef0"
      iam_instance_profile = ""
    }
  }

  assert {
    condition     = aws_ec2_tag.deployment.resource_id == var.instance_id && aws_ec2_tag.deployment.key == "HuginnDeployment" && aws_ec2_tag.deployment.value == "huginn-production"
    error_message = "Only the deployment tag on the existing instance should be managed."
  }

  assert {
    condition     = jsondecode(aws_iam_role.github_deployment.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:KhaledAwashreh@40263357/Huginn@1360631904:environment:production"
    error_message = "OIDC trust must name this repository's immutable production subject."
  }

  assert {
    condition     = jsondecode(aws_iam_role.github_deployment.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    error_message = "OIDC trust must validate the AWS audience."
  }

  assert {
    condition     = jsondecode(aws_iam_role_policy.github_deployment.policy).Statement[2].Condition.StringEquals["ssm:resourceTag/HuginnDeployment"] == "huginn-production"
    error_message = "Run Command must be restricted to the deployment tag."
  }

  assert {
    condition     = jsondecode(aws_iam_role_policy.github_deployment.policy).Statement[1].Resource == "arn:aws:ssm:eu-north-1::document/AWS-RunShellScript"
    error_message = "Only the AWS-managed shell document may be sent."
  }

  assert {
    condition     = length(aws_iam_instance_profile.ssm) == 1 && length(aws_iam_role.ssm) == 1
    error_message = "An instance without a profile needs one SSM role/profile for manual attachment."
  }

  assert {
    condition     = output.instance_profile_attachment_required
    error_message = "A newly created profile must be explicitly attached by the operator."
  }
}

run "preserves_existing_instance_profile" {
  command = plan

  override_data {
    target = data.aws_instance.target
    values = {
      id                   = "i-0123456789abcdef0"
      iam_instance_profile = "existing-application-profile"
    }
  }

  override_data {
    target = data.aws_iam_instance_profile.existing[0]
    values = {
      role_name = "existing-application-role"
      arn       = "arn:aws:iam::123456789012:instance-profile/existing-application-profile"
    }
  }

  assert {
    condition     = length(aws_iam_instance_profile.ssm) == 0 && length(aws_iam_role.ssm) == 0
    error_message = "An existing profile must not be replaced."
  }

  assert {
    condition     = aws_iam_role_policy_attachment.ssm.role == "existing-application-role" && aws_iam_role_policy_attachment.ssm.policy_arn == "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
    error_message = "Only SSM permissions should be added to the existing role."
  }
}

run "retains_created_profile_after_operator_attachment" {
  command = plan

  override_data {
    target = data.aws_instance.target
    values = {
      id                   = "i-0123456789abcdef0"
      iam_instance_profile = "huginn-deployment-ssm"
    }
  }

  assert {
    condition     = length(aws_iam_instance_profile.ssm) == 1 && length(aws_iam_role.ssm) == 1 && !output.instance_profile_attachment_required
    error_message = "Manual attachment must not make Terraform delete its own profile."
  }
}

run "reuses_account_oidc_provider" {
  command = plan

  variables {
    existing_oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
  }

  override_data {
    target = data.aws_instance.target
    values = {
      id                   = "i-0123456789abcdef0"
      iam_instance_profile = ""
    }
  }

  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 0 && jsondecode(aws_iam_role.github_deployment.assume_role_policy).Statement[0].Principal.Federated == var.existing_oidc_provider_arn
    error_message = "An existing account-wide OIDC provider should be reused."
  }
}
