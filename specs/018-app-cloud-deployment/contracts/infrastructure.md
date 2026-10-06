# Contract: Infrastructure stacks and permissions

OpenTofu `1.10.6`, AWS provider `~> 6.0` (the same as the pipeline repo), with lock files hashed for `linux_arm64`, `linux_amd64` and `darwin_arm64`. State lives in the shared bucket from the account setup, under `app/<env>/`.

## Stacks

| Stack | Applied by | When | State key | Contains |
|---|---|---|---|---|
| `infra/base` | owner, admin credentials, laptop | once per env, then rarely | `app/<env>/base.tfstate` | CI roles (`plan`, `release`, `deploy`), instance role and instance profile, ECR repositories `cloud-pricing-app-backend-<env>` and `cloud-pricing-app-web-<env>` (immutable tags, scan-on-push, keep the newest 5 tagged, untagged expire after 1 day, `force_delete = false`), backup bucket, log group, alert topic and subscription, allowlist parameter |
| `infra/instance` | `deploy/app` (CI `deploy` role or the owner) | every up, down and allow | `app/<env>/instance.tfstate` | VPC, public subnet, IGW, route table, security group (443 from the allowlist only), EC2 instance with user-data |

**Inputs that refer to account-wide items** (never created here, FR-056):

- `state_bucket_name`
- `github_oidc_provider_url` (`token.actions.githubusercontent.com`), looked up with `data "aws_iam_openid_connect_provider"`
- `data_bucket_name` and `data_read_policy_name`, from the pipeline's data stack, looked up with data sources

If any of these is missing, the data source lookup fails during the plan, before anything is created, and the provider's error names the item. Don't add `precondition` blocks for them: a precondition never runs when its lookup fails. The runbook's one-time setup lists a check command for each item that names it (FR-046, FR-056).

**Tags on every resource**: `app = "cloud-pricing-app"` and `environment = <env>`. The instance stack also tags `release = <tag>`.

## `deploy` role permissions (per env)

| Statement | Actions | Scope |
|---|---|---|
| State | `s3:GetObject/PutObject/DeleteObject` | `<state-bucket>/app/<env>/*`, including `.tflock` |
| State list | `s3:ListBucket` | the state bucket, `s3:prefix` `app/<env>/*` |
| Network create | `ec2:Create*` (VPC, subnet, internet gateway, route table, security group) | `*`, with `aws:RequestTag/environment = <env>` and `aws:RequestTag/app = cloud-pricing-app` |
| Tag on create | `ec2:CreateTags` | `ec2:CreateAction` in the create actions above, including `AuthorizeSecurityGroupIngress` and `RunInstances` |
| Change and delete own | `ec2:*` (except create) | `aws:ResourceTag/environment = <env>` and `aws:ResourceTag/app = cloud-pricing-app` |
| Security group rules | `ec2:AuthorizeSecurityGroupIngress/Egress`, `ec2:RevokeSecurityGroupIngress/Egress` | `security-group-rule/*` with the request tag, and the env's tagged security group |
| Launch: created resources | `ec2:RunInstances` | `instance/*` with `aws:RequestTag/environment` and `aws:RequestTag/app`; `volume/*` and `network-interface/*` without a tag condition. RunInstances creates all three and AWS authorizes each, so the parts can only be created together with a tagged instance in a tagged subnet — the action can't create them on their own. The AWS provider doesn't reliably send tags for the network interface, so requiring request tags there would fail the launch |
| Launch: used resources | `ec2:RunInstances` | `arn:aws:ec2:<region>::image/*` limited by `ec2:Owner = amazon` and `ec2:Public = true` — public images from AWS and its verified publishers (Canonical's Ubuntu AMIs carry the owner alias `amazon`, which is what `ec2:Owner` evaluates; a condition on Canonical's account ID never matches), not one pinned AMI; the exact AMI is pinned in `<env>.tfvars`, and updating it needs no base-stack apply. The env's `subnet/*` and `security-group/*`, with `aws:ResourceTag/environment = <env>`. No key pair is used |
| Pass role | `iam:PassRole` | the env's instance role only, `iam:PassedToService = ec2.amazonaws.com` |
| SSM commands: document | `ssm:SendCommand` | `arn:aws:ssm:<region>::document/AWS-RunShellScript` only (an AWS-owned document ARN has no account ID) |
| SSM commands: target | `ssm:SendCommand` | `arn:aws:ec2:<region>:<account>:instance/*`, with **`ssm:resourceTag/environment = <env>`** and `ssm:resourceTag/app = cloud-pricing-app`. Run Command uses the `ssm:resourceTag/…` key, not `aws:ResourceTag/…` |
| SSM results | `ssm:GetCommandInvocation`, `ssm:ListCommandInvocations` | `*` (to be confirmed against the Service Authorization Reference while writing the policy) |
| Parameters | `ssm:GetParameter(s)`, `ssm:PutParameter` | `parameter/cloud-pricing-app/<env>/*` (no `DeleteParameter`) |
| Lock | `s3:GetObject/PutObject/DeleteObject` | `<backup-bucket>/locks/<env>.json` |
| Backups listing (status) | `s3:ListBucket` | the backup bucket, prefix `<env>/db/` |
| Notify | `sns:Publish` | the env's topic |
| Resolve release | `ecr:DescribeImages` | the env's two repositories |
| Read-only discovery | `ec2:Describe*`, `sts:GetCallerIdentity`, `ssm:GetParameter` on `/aws/service/canonical/*` | `*` |

The `plan` role has the state read statements, `ec2:Describe*`, parameter read and the discovery statement only.

## `release` role permissions (per env)

| Statement | Actions | Scope |
|---|---|---|
| Registry login | `ecr:GetAuthorizationToken` | `*` (no resource ARN) |
| Push and check | `ecr:BatchCheckLayerAvailability`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:PutImage`, `ecr:DescribeImages`, `ecr:BatchGetImage` | the env's two repositories |

Trust: `…:ref:refs/tags/v*` only. No state access and no other services.

## Instance role: registry pull

`ecr:GetAuthorizationToken` (`*`), and `ecr:BatchGetImage` and `ecr:GetDownloadUrlForLayer` on the env's two repositories.

**Checked against AWS documentation (2026-10-02)**:

- **`CreateTags` on create**: tagging at create time needs `ec2:CreateTags` with the `ec2:CreateAction` condition ([EC2 tagging on creation](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/supported-iam-actions-tagging.html)).
- **`RunInstances` resources**: RunInstances is authorized against the image, instance, subnet, network interface, volume, security group and key pair ([VPC policy examples](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-policy-examples.html)).
- **Run Command tags**: Run Command is limited by `ssm:resourceTag/<key>` on the instance, plus a separate document statement ([Run Command setup](https://docs.aws.amazon.com/systems-manager/latest/userguide/run-command-setting-up.html)).

**Still to confirm while writing the policy JSON** (a task, not a planning gap):

- Which actions accept only `Resource: *`, from the Service Authorization Reference for EC2, SSM and ECR.
- That `amazon-ecr-credential-helper` is in the Ubuntu 24.04 arm64 archive.

## Verified action list (T026, 2026-10-02)

Checked against the machine-readable Service Authorization Reference (`https://servicereference.us-east-1.amazonaws.com/v1/<service>/<service>.json`, the same data as the published reference pages). "`*` only" means the action has no resource type, so a statement for it must use `Resource: "*"`.

| Action | Resource types AWS checks | `*` only | Condition keys this repo uses |
|---|---|---|---|
| `ssm:SendCommand` | `document`, `instance` (also `managed-instance`, `bucket` — not used) | no | `ssm:resourceTag/environment`, `ssm:resourceTag/app` on `instance/*`. The document statement names `document/AWS-RunShellScript` |
| `ssm:GetCommandInvocation` | — | **yes** | none |
| `ssm:ListCommandInvocations` | — | **yes** | none |
| `ssm:DescribeInstanceInformation` | — | **yes** | none (used to wait for the agent to come online) |
| `ssm:GetParameter(s)`, `ssm:PutParameter` | `parameter` | no | parameter path `/cloud-pricing-app/<env>/*`; public `/aws/service/canonical/*` for `ami-latest` |
| `ec2:Describe*` (incl. `DescribeImages`, `DescribeInstances`) | — | **yes** | none |
| `ec2:RunInstances` | `image`, `instance`, `network-interface`, `security-group`, `subnet`, `volume` (plus types not used: key pair, launch template, snapshot, …) | no | `aws:RequestTag/*` on `instance/*`; `aws:ResourceTag/*` on `subnet/*` and `security-group/*`; `image/*` with `ec2:Owner = amazon` and `ec2:Public = true` (verified publishers, including Canonical; the AMI itself is pinned in tfvars, not in IAM). `network-interface/*` and `volume/*` are allowed without a tag condition: they are created only alongside an instance that must carry the tags, in a subnet that must carry them |
| `ec2:CreateTags` | every EC2 type | no | `ec2:CreateAction` in `CreateVpc`, `CreateSubnet`, `CreateInternetGateway`, `CreateRouteTable`, `CreateSecurityGroup`, `AuthorizeSecurityGroupIngress`, `AuthorizeSecurityGroupEgress`, `RunInstances` |
| `ec2:CreateVpc`, `CreateInternetGateway` | `vpc` / `internet-gateway` | no | `aws:RequestTag/environment`, `aws:RequestTag/app` |
| `ec2:CreateSubnet`, `CreateRouteTable`, `CreateSecurityGroup` | the new resource **and** the `vpc` | no | `aws:RequestTag/*` (request-wide, so it covers the VPC check too) |
| `ec2:AuthorizeSecurityGroupIngress/Egress` | `security-group`, `security-group-rule` | no | `aws:RequestTag/*` for the new rule; `aws:ResourceTag/*` for the group |
| `ec2:RevokeSecurityGroupIngress/Egress` | `security-group` only | no | `aws:ResourceTag/*` |
| `ec2:CreateRoute`, `AttachInternetGateway`, `AssociateRouteTable`, `Modify*Attribute`, `Delete*`, `TerminateInstances` | the existing (tagged) resources | no | `aws:ResourceTag/*` |
| `ecr:DescribeImages`, `BatchGetImage`, `GetDownloadUrlForLayer`, push actions | `repository` | no | repository ARN |
| `ecr:GetAuthorizationToken` | — | **yes** | none |
| `sns:Publish` | `topic` | no | topic ARN |
| `logs:CreateLogStream`, `PutLogEvents` | `log-stream` | no | `log-group:/cloud-pricing-app/<env>:log-stream:*` |
| `iam:PassRole` | `role` | no | `iam:PassedToService = ec2.amazonaws.com` |

**Approved `Resource: "*"` statements** (base-stack test 6 checks this list): the `*`-only actions above (`ec2:Describe*`, `ssm:GetCommandInvocation`, `ssm:ListCommandInvocations`, `ssm:DescribeInstanceInformation`, `ecr:GetAuthorizationToken`, `sts:GetCallerIdentity`), and EC2 statements that carry an `aws:RequestTag`, `aws:ResourceTag` or `ec2:CreateAction` condition.

**State bucket listing**: `s3:ListBucket` on the state bucket is granted without a prefix condition, as in the pipeline's `apply` role. The S3 backend lists keys outside `app/<env>/` (workspaces, under `env:/`) during `init`, and a listing reveals key names only. Objects stay limited to `app/<env>/*`.

**Not needed**: KMS permissions for the `aws/ssm` key on the `deploy` role. AWS-managed key policies already allow any principal in the account that is authorized to call SSM (`kms:ViaService`, `kms:CallerAccount`). The instance role keeps an explicit `kms:Decrypt` with `kms:ViaService` as task T027 asks, which is harmless.

## Tests that must exist (`tofu test`, mocked providers, run in CI)

1. `instance`: there is no `aws_s3_bucket*`, `aws_ssm_parameter`, `aws_cloudwatch_log_group`, `aws_sns_*` or `aws_iam_*` resource (nothing long-lived, and no IAM writes).
2. `instance`: the security group's ingress is exactly port 443 from each allowlist entry. There is no 22, no 80 and no `0.0.0.0/0` ingress.
3. `instance`: `metadata_options.http_tokens = "required"`, the root volume is encrypted with `delete_on_termination = true`, and `associate_public_ip_address = true`. No Elastic IP.
4. `base`: no `aws_instance` or `aws_vpc`. The backup bucket blocks public access and is encrypted. Both ECR repositories are `IMMUTABLE`, scan on push, have the lifecycle policy, and are not force-deletable.
5. `base`: the trust subjects equal the expected strings for `plan`, `release` and `deploy` (output `gha_trust_subjects`). The `release` role's only non-`*` resources are the env's two repositories.
6. `base`: every `deploy` statement with `resources = ["*"]` is in an approved list (discovery and SSM results) or carries a tag condition.
