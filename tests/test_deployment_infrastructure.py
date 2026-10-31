"""Keep deployment bootstrap outside ownership of the running application host."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "infrastructure/aws-deployment"


def test_bootstrap_cannot_manage_instances_disks_networking_or_command_provisioners():
    resources = set()
    for path in ROOT.glob("*.tf"):
        content = path.read_text()
        resources.update(re.findall(r'\bresource\s+"([^"]+)"', content))
        assert not re.search(r'\bprovisioner\s+"', content), path
    assert resources
    assert resources <= {
        "aws_ec2_tag",
        "aws_iam_role",
        "aws_iam_role_policy",
        "aws_iam_role_policy_attachment",
        "aws_iam_instance_profile",
        "aws_iam_openid_connect_provider",
    }
