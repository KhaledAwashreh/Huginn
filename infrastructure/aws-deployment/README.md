# Set up automatic EC2 deployment

This bootstrap configures GitHub's AWS deployment role, its OIDC trust, the
existing EC2 instance's deployment tag and the instance role's Systems Manager
permissions. It does not manage the EC2 instance, disks, network rules, Docker,
application configuration or database. Application releases still use the
[CI deployment job](../../.github/workflows/ci.yml), not Terraform.

Run these commands from this directory on your own computer. You need Terraform
1.11+ and an authenticated AWS operator identity with permission to read the
instance, manage these IAM resources and set its tag. Use an AWS CLI profile or
temporary credentials through the normal AWS credential chain; do not put access
keys in Terraform files or GitHub. Confirm the account with
`aws sts get-caller-identity` before planning.

## Prepare

1. Copy the existing instance ID from the EC2 console. This is an `i-...` value,
   not its public IP. The default region is Stockholm, `eu-north-1`.
2. In **IAM → Identity providers**, check whether
   `token.actions.githubusercontent.com` already exists. If so, copy its ARN and
   confirm its audience includes `sts.amazonaws.com`. Reuse it below instead of
   creating another account-wide provider.
3. Create an ignored `terraform.tfvars` in this directory:

   ```hcl
   instance_id = "i-YOUR_EXISTING_INSTANCE_ID"

   # Set only when the account already has this GitHub identity provider:
   # existing_oidc_provider_arn = "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
   ```

   `aws_region` and `deployment_tag_value` default to `eu-north-1` and
   `huginn-production`. The IAM namespace defaults to `huginn-deployment`; keep
   it stable after applying. Do not reuse that namespace for unrelated roles or
   profiles. If those names already exist outside this state, stop and resolve
   ownership rather than deleting them.

## Review and apply once

```sh
terraform init
terraform fmt -check -recursive
terraform validate
terraform test
terraform plan -out=bootstrap.tfplan
terraform apply bootstrap.tfplan
terraform output
```

Review the plan before the explicit apply. Expected changes are IAM resources,
one EC2 tag, and an SSM policy attachment. There must be no instance, disk,
network or database creation, replacement or deletion. The automated tests use
a mock AWS provider and make no AWS calls. `plan` and `apply` use real AWS.

The provider lockfile is tracked; `.terraform`, variable files, plans and local
state are ignored. Keep a private backup of the state and its lockfile, and run
later updates from the same state. This first version uses local state rather
than provisioning another storage service. IAM roles, profiles and a created
OIDC provider have destruction protection; do not remove that protection or run
`destroy` as an application update step.

## Finish the instance setup

If the instance already has an IAM profile, Terraform reads it and adds only
`AmazonSSMManagedInstanceCore` to its existing role. It does not replace the
profile or alter its trust/other policies. If that role is shared, the added SSM
permission also applies to the other instances using it.

If `instance_profile_attachment_required` is `true`, Terraform created a profile
for this instance but did not change its profile association. In **EC2 → select
instance → Actions → Security → Modify IAM role**, select the name printed by
`instance_profile_name` and save. This is one operation on the existing instance;
do not create or import an `aws_instance` resource to perform it. The next plan
retains the created profile after attachment rather than deleting it.

Ensure SSM Agent is installed, running and the instance is **Online** under
Systems Manager managed nodes. The agent needs outbound HTTPS to AWS Systems
Manager endpoints; the app also needs GitHub/GHCR access. See the
[AWS EC2 setup guide](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-setting-up-ec2.html).
Terraform does not install software or run commands on your instance.

Keep the existing working Huginn checkout and `.env`, normally owned by `ubuntu`
under `/home/ubuntu/Huginn`. That owner must be able to run
`sudo -n docker compose version`. Authenticate private GHCR pulls once in the
root Docker context with `sudo docker login ghcr.io`. See the
[registry setup](../../docs/docker-compose.md#pull-a-published-image-on-ec2).

## Connect GitHub

1. In **repository Settings → Environments**, create `production`. Restrict its
   deployment branches to **master**. The OIDC trust names the environment;
   branch enforcement is this environment rule. Leave required-reviewer approval
   disabled for deployment after every successful release without another click.
2. Run `terraform output github_actions_variables`. In **Settings → Secrets and
   variables → Actions → Variables**, add the printed `AWS_DEPLOY_ROLE_ARN`,
   `AWS_REGION` and `EC2_DEPLOY_TAG_VALUE` values. These are variables, not secrets.
3. The workflow defaults to Linux user `ubuntu` and `/home/ubuntu/Huginn`. Set
   `EC2_DEPLOY_USER` and `EC2_DEPLOY_PATH` only if your existing checkout differs.
4. Merge the reviewed pipeline change, then confirm `deploy-ec2` succeeds after
   image publication. No inbound deployment port, stored private key, public IP
   setting or long-lived AWS access key is needed by the job.

The trust uses this repository's verified immutable GitHub subject:
`repo:KhaledAwashreh@40263357/Huginn@1360631904:environment:production`.
This bootstrap is intentionally specific to this repository. A fork needs its
own exact subject. See [GitHub's AWS OIDC setup](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

The role can send `AWS-RunShellScript` only to instances carrying the deployment
tag. Exactly one running tagged instance must exist in the chosen region.
Protect access to the tag and deployment role: Run Command executes administrative
commands on the permitted host. Read/discovery API permissions use `Resource: "*"`
because those APIs do not support per-instance resource restrictions. See
[AWS Run Command permissions](https://docs.aws.amazon.com/systems-manager/latest/userguide/run-command-setting-up.html).

For release behavior, timeouts and recovery, use the
[deployment guide](../../docs/docker-compose.md#release-behavior-and-recovery).
