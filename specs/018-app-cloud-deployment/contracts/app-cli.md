# Contract: `deploy/app` command and the `app` workflow

The same script runs on the owner's laptop and in GitHub Actions (`.github/workflows/app.yml`, `workflow_dispatch`). Both take the environment and region explicitly. See [configuration.md](./configuration.md).

```text
deploy/app <command> --env <dev|qa|prod> [options]
```

## Commands

| Command | Does | Takes the lock |
|---|---|---|
| `up [--release vX.Y.Z] [--backup <id>] [--new-root] [--break-lock]` | Preflight (including: the release exists in both of the env's ECR repositories), then resolve the release to digests, ensure the TLS root, apply the instance stack, wait for health through SSM, and notify | yes |
| `down [--force-without-backup] [--break-lock]` | Final backup through SSM, which must be verified, then destroy the instance stack | yes |
| `status` | Instance state, address, uptime, release, last backup (id, kind, verified), lock holder. If the instance is running, it also sends the address notice (`ops notify` through SSM), because the address is masked in GitHub logs (FR-038) | no |
| `allow add <ip>` / `allow remove <ip>` / `allow list` | Edit the allowlist parameter and print the full list. If the instance is up, apply the instance stack using the running instance's own values (from the instance-stack outputs), and refuse with exit 3 if the plan would replace the instance (FR-029). On that refusal, the previous allowlist value is written back, so nothing changes | yes (add and remove) |
| `cert [--out file]` | Print or save the env's public root certificate. `cert local --create` makes a laptop root for the local packaged stack | no |
| `ami-latest` | Print the newest Canonical Ubuntu 24.04 arm64 AMI ID for the region, to paste into `<env>.tfvars` | no |
| `backup-now` | Run `ops backup --kind manual` on the instance through SSM | yes |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. For `up`, pricing may still be unavailable, which is reported as a warning in the output and the notice. |
| `2` | Usage or validation error (bad env, bad IP, unknown release). Nothing changed. |
| `3` | Precondition not met (preflight item missing, release has no images, lock held, root missing with existing backups, `allow` would replace the instance). Nothing changed. |
| `4` | `down`: the backup failed or wasn't verified. Nothing destroyed. |
| `5` | `up`: the instance didn't become healthy. The stack is left for diagnosis, and `up` or `down` can be run again. |
| other | Unexpected failure. The step name is printed. |

## Guarantees

- **Explicit inputs**: region, environment and account come only from arguments, variables and the credential chain (FR-048).
- **Real outcomes**: every AWS call's result is checked. SSM commands are polled to a terminal status, and anything other than `Success` fails, with the command's stderr tail printed (FR-047).
- **Lock**: the lock is always released on exit (`trap`), except that a crash leaves it to expire. It can be broken after 2 hours (FR-030).
- **Repeatable**: `up` always plans first (`tofu plan -out`). If the plan replaces or destroys a running instance, for any reason (release digests, AMI, `db_init_args`), it first takes and verifies a `redeploy` backup, exactly like `down` and stopping on failure, then applies the saved plan. The new instance restores from that backup (FR-029, FR-057). If the plan doesn't touch the instance, `up` applies it and re-checks health. There is one deployment path and no in-place upgrade. `down` on a stopped env succeeds (FR-029).
- **Hygiene in GitHub**: the address, any IP input and account IDs are masked. Role ARNs come from secrets (FR-050).

## `app.yml` workflow

- **Trigger**: `workflow_dispatch`, with inputs `action` (`up|down|status|allow-add|allow-remove|allow-list|backup-now`), `environment`, `release`, `backup`, `address`, `force_without_backup` (bool).
- **Job**: `environment: ${{ inputs.environment }}`, `concurrency: app-${{ inputs.environment }}` (queued, not cancelled), `permissions: id-token: write, contents: read`.
- **Steps**:
  1. mask inputs
  2. checkout (pinned SHA)
  3. setup OpenTofu `1.10.6`
  4. configure AWS credentials with the `deploy` role and account-ID masking
  5. `deploy/app <action> …`

## `release.yml` workflow

Triggered by a `v*` tag push, or run manually with a `tag` input to re-publish an existing tag to a newly added environment. It runs on `ubuntu-24.04-arm` with a matrix over `RELEASE_ENVIRONMENTS` (default `prod`). For each environment:

1. Assume `cloud-pricing-app-gha-release-<env>` with account-ID masking.
2. Check whether `cloud-pricing-app-{backend,web}-<env>:<tag>` already exists (`ecr:DescribeImages`). Existing images are skipped, because tags are immutable.
3. Build and push the missing images for `linux/arm64`, labelled with the git SHA.
4. Write their digests to the job summary.

The step checks the push result and fails on any error (FR-047).

## `oidc-subject.yml` workflow

Manual. Prints `sub`, `ref`, `environment` and `event_name` of the job's token (never the token itself), to check against `tofu output gha_trust_subjects` in `infra/base` (FR-051).
