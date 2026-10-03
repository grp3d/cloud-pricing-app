# Research: On-Demand Cloud Deployment with Manifest-Driven Pricing Data

**Feature**: `018-app-cloud-deployment` | **Date**: 2026-10-02 | **Spec**: [spec.md](./spec.md)

Each section records a decision, why it was made, and what else was considered. Per FR-058, every decision also lists what it **adds** to configuration and operations. The full inventory is in [plan.md § Configuration inventory](./plan.md#configuration-inventory-fr-058).

Facts checked while researching (2026-10-02):

- This repository is **public** (`grp3d/cloud-pricing-app`, id `1378579975`, created 2026-09-20). Its OIDC subject template is the **default** (`use_default: true`), with the immutable prefix `repo:grp3d@5554338/cloud-pricing-app@1378579975`.
- The account's existing setup (data-retrieval `infra/bootstrap`) provides the OIDC provider for `token.actions.githubusercontent.com`, the state bucket `cloud-pricing-shared-tfstate-g08a9i` (`us-east-1`, S3 native locking), and the account budget. Its CI roles trust only the data-retrieval repo. The pipeline's apply role can write state under `prod/*`.
- The data stack publishes bucket `cloud-pricing-data-prod-g08a9i` and the managed policy output `data_read_policy_arn` (`cloud-pricing-data-read-prod`). That policy can list only `aws/manifests/*` and `aws/parquet/*`.
- Today's code builds Parquet paths as `…/<table>/snapshot_date=<D>/region=<R>/part-0.parquet` in `pricing.py` and `catalog.py`. The new layout names files `part-<run_id>[-n].parquet` and allows more than one per region, so **every** path builder must take its file list from the manifest.
- The only local data is the legacy tree `DATA/pricing_aws/`. No new-layout local root exists yet.
- The owner's laptop is `arm64` (Apple silicon), and Docker is not installed on it.
- Auth today: the bearer token *is* the user's UUID, unknown UUIDs create guest users, and migration `0004` seeds `Admin` with the password `admin123`. Accounts with no password are claimed by whoever logs in first. See R17.

---

## R1. Where the app's deployment roles and long-lived resources live

**Decision**: This repository has a **base stack** (`infra/base`), applied once per environment by the owner from a laptop with administrator credentials. It creates:

- the environment's CI roles, `plan`, `release` and `deploy` (R2)
- the two ECR repositories for release images (R5)
- the backup bucket, which also holds the operation lock
- the log group
- the alert topic and its email subscription
- the allowlist parameter

It **refers to** the account-wide items (the OIDC provider and the state bucket) through explicit inputs and data sources. It never creates or changes them. Its state lives in the shared state bucket under the key prefix `app/<env>/`, outside the pipeline roles' `prod/*` prefix and vice versa.

The **instance stack** (`infra/instance`) holds everything disposable and is the only thing "up" and "down" apply or destroy.

**Rationale**:

- It is the decision recorded in the spec Clarifications (FR-056).
- The pipeline's R1 finding came from long-lived resources sitting in the disposable stack. Here, nothing long-lived is ever in the stack that "down" destroys (FR-032).
- Applying long-lived resources from the laptop keeps the CI `deploy` role down to instance-stack permissions only. That is the smallest permission set that can be complete, and it addresses the "permissions found one failure at a time" lesson (FR-049).

**Alternatives considered**:

- Extending the data-retrieval bootstrap: rejected in clarification.
- A separate "persistent" stack applied by CI: rejected because it gives the CI role bucket, IAM and SNS permissions just to change things that change about once a year.
- A third shared account repository: deferred. Account items are referenced only by inputs, so a later move doesn't touch the app.

**Adds**: one stack applied by hand per environment (rarely re-applied), and three inputs (`state_bucket_name`, `github_oidc_provider_url`, `alert_email`).

## R2. CI roles and trust

**Decision**: Three roles per environment.

| Role | Trusted subject (repo template `["repo","context","ref"]`) | Can do |
|---|---|---|
| `cloud-pricing-app-gha-plan-<env>` | `…:pull_request:ref:refs/pull/*/merge` | Read state `app/<env>/*`, read-only describe calls for the instance stack's resource types, read the allowlist parameter. |
| `cloud-pricing-app-gha-release-<env>` | `…:ref:refs/tags/v*` (both renderings of a plain tag run, as the pipeline's `run` role does for `main`) | `ecr:GetAuthorizationToken` (no resource ARN), and push and describe actions on the env's two repositories only. Nothing else. |
| `cloud-pricing-app-gha-deploy-<env>` | `…:environment:<env>:ref:refs/heads/main` | Read/write state `app/<env>/*`. Create, change and delete the instance stack's resources (tag-scoped `environment=<env>`, `app=cloud-pricing-app`). Send SSM commands to instances with those tags. Read/write the env's SSM parameters under `/cloud-pricing-app/<env>/`. Read/write the operation lock in the backup bucket. Publish to the env's alert topic. `iam:PassRole` only for the instance role. |

- The subject template is set once per repo, a runbook step that needs a temporary personal access token, as in the pipeline repo. A `oidc-subject` workflow prints the real token subject so the trust can be checked before the first deploy (FR-051).
- Role ARNs are stored as GitHub **secrets**, and every AWS login uses `mask-aws-account-id: true` (FR-050).
- The `deploy` role does **not** trust release tags. A tag push can only assume the `release` role, which can push images to the env's two repositories and do nothing else (R5). A GitHub ruleset limits who can create `v*` tags.
- The **instance role and its instance profile** are created in the base stack, not the instance stack. The deploy role then needs no IAM write permission at all, only `iam:PassRole` on that one named role.

**Rationale**: FR-049 asks for identities separated by purpose. A third "operate" role (status, allowlist) would have the same reach as `deploy`, because both act only on the env's own instance and parameters. Splitting them adds a role, a trust rule and a secret with no real narrowing, so the plan has no separate operate role. Publishing images is a different purpose, reached from tags rather than `main`, so it gets its own push-only role. Spec FR-049 is updated to say "preview", "publish release images" and "change". Account-wide prerequisites that the deploy role can't create are listed in the runbook and checked by a preflight. For example, the EC2 Spot service-linked role is not needed, and the SSM default host management setting is not used. See R11 for the full first-run checklist.

**Alternatives considered**: a separate operate role (above). Letting the deploy role trust `v*` tags so it can also push: a tag job would then hold full deploy rights.

**Adds**: three roles per env; GitHub secrets `AWS_ROLE_PLAN_<ENV>`, `AWS_ROLE_DEPLOY_<ENV>` and `AWS_ROLE_RELEASE_<ENV>`; the variable `AWS_REGION`; and one GitHub environment per env.

## R3. Compute: one small ARM instance running Docker Compose

**Decision**: One EC2 instance, `t4g.small` (2 vCPU burstable, 2 GiB RAM, arm64), with a 2 GiB swap file and a 20 GiB encrypted gp3 root volume that is deleted on termination. It runs in its own VPC with one public subnet, an internet gateway and no NAT, created and destroyed with the instance stack. It gets an auto-assigned public IPv4 address, so the address changes every bring-up and costs nothing while down. IMDSv2 is required.

**Cost check (us-east-1, on-demand; confirmed with the AWS Price List API on 2026-10-02: t4g.small $0.0168/h, gp3 $0.08/GB-month, ECR $0.10/GB-month, public IPv4 $0.005/h)**:

| Item | Up 24/7 per month | Down per month |
|---|---|---|
| t4g.small | $12.26 | $0 |
| gp3 20 GiB | $1.60 | $0 |
| Public IPv4 | $3.65 | $0 |
| CloudWatch Logs (≈0.2 GB) | ≈$0.10 | ≈$0.02 |
| Backups in S3 (14 × a few MB) | ≈$0.01 | ≈$0.01 |
| ECR (2 repos, ≤5 images each, ≈250 MB per image, less with shared layers) | ≈$0.25 | ≈$0.25 |
| SSM parameters (standard tier), state | $0 | $0 |
| **App total** | **≈$17.9** | **≈$0.30** |

Adding the pipeline (weekly Fargate runs plus S3) keeps 24/7 use under the $20–30 cap (SC-009).

**Memory**: DuckDB queries read one region's files at a time, and a full snapshot is ≈145 MB. The backend sets DuckDB's `memory_limit` to 512 MB and `threads` to 2 through two new settings (`DUCKDB_MEMORY_LIMIT`, `DUCKDB_THREADS`), which also keep laptop behavior bounded. Postgres runs with `shared_buffers=128MB`. **Measure before accepting**: a task records peak RSS across the standard-architecture pricing tests on the instance. If it doesn't fit, the fallback is `t4g.medium`, which is within the cap only when the app is not up 24/7. That would be recorded as a spec change, not a silent swap.

**Alternatives considered**:

- `t4g.medium` (4 GiB): $24.5/month alone at 24/7, which breaks the cap with the pipeline.
- Spot instances: about 70% cheaper, but interruptions add a "lost instance mid-backup" path plus a service-linked role. Rejected for now (complexity, FR-058).
- ECS or Fargate: contradicts the Compose decision and needs a load balancer or a public task IP plus more IAM.
- The default VPC: it may not exist in every account and can't be tag-scoped for permissions.

**Adds**: the instance stack (VPC, subnet, IGW, route table, security group, instance profile, instance), and two backend settings (`DUCKDB_MEMORY_LIMIT`, `DUCKDB_THREADS`).

## R4. Host OS and how the stack starts

**Decision**: **Ubuntu 24.04 LTS arm64**, with the AMI ID **pinned** per environment in `infra/envs/<env>.tfvars` and an `app ami-latest` helper that prints the newest Canonical ID from the public SSM parameter for a deliberate update. cloud-init (user-data, rendered by OpenTofu, gzip-compressed) does the following:

1. Installs `docker.io`, `docker-compose-v2` and `amazon-ecr-credential-helper` from the Ubuntu archive. These are apt-signed, so there is no hand-pinned binary to checksum. It points Docker at the helper for the account's ECR registry, so pulls use the instance role.
2. Writes `/opt/app/compose.yaml`, `/opt/app/.env` (non-secret settings, image digests, the public IP from IMDS) and two systemd timers (R10).
3. Runs `docker compose up -d`.

The SSM agent ships with Ubuntu's official AMIs. The host never runs the AWS CLI. Image pulls go through the credential helper, and every AWS call (secrets, backups, alerts, pricing data) is made from the backend image with boto3, using the instance role.

**Rationale**: Amazon Linux 2023 has no Compose plugin package, so it would need a downloaded binary with a hand-maintained checksum. That is exactly the R2 upgrade trap in the pipeline repo. Ubuntu's packages remove it.

**Alternatives considered**: AL2023 plus a pinned Compose binary, Bottlerocket (no Compose), and baking a custom AMI (another build pipeline).

**Adds**: one pinned AMI ID per env and a helper subcommand.

## R5. Release images and registry

**Decision**: **Amazon ECR**, the same registry as the pipeline, chosen by the owner for consistency across the project (2026-10-02).

**Images**: two images per release tag `v*`, built by `release.yml` natively on GitHub's `ubuntu-24.04-arm` runners for **linux/arm64 only**. Both the server and the owner's laptop are arm64, so there's no QEMU.

- **Repositories**: `cloud-pricing-app-backend-<env>` (FastAPI app, migrations, ops CLI (R8–R10), boto3 and `postgresql-client-18`) and `cloud-pricing-app-web-<env>` (Caddy plus the built frontend).
- **Where they live**: in the **base stack**, which "down" never touches. That avoids the pipeline's R1 problem: the repositories always exist before the first push and survive every teardown.
- **Repository settings**:
  - tag mutability `IMMUTABLE` (FR-018)
  - basic scan-on-push
  - lifecycle: keep the newest 5 tagged images, expire untagged after 1 day
  - `force_delete = false`, so a stray destroy of the base stack fails instead of deleting releases
- **Pushing**: `release.yml` runs on a `v*` tag. For each environment in the GitHub variable `RELEASE_ENVIRONMENTS` (default `prod`), it assumes that env's `release` role (R2), skips any image whose tag already exists (as the pipeline does), and builds and pushes the rest.
- **Pulling**: the instance pulls with its instance role through the **Amazon ECR credential helper** (`amazon-ecr-credential-helper`, an Ubuntu archive package, apt-signed). That means no stored registry credentials and no AWS CLI on the host. "Up" resolves each tag to its **digest** with `ecr:DescribeImages`, deploys by digest, and records both in the instance's `.env`.

**Choosing the release (FR-057)**: with no input, "up" picks the highest semver `v*` tag present in **both** of the env's repositories. A named release missing from either repository fails before anything is created. Only the newest 5 releases can be deployed, so rollback reaches back at most 4 releases. An older release fails preflight with "release vX.Y.Z is no longer in this environment's registry". Re-running `release.yml` for that tag rebuilds and pushes it.

**Rationale**:

- One registry for the whole project, so one place to look and one way to work.
- Tag immutability and vulnerability scanning come from the registry rather than workflow rules.
- Images stay private.
- Bring-up doesn't depend on GitHub's registry.
- Putting the repositories in the base stack and giving pushes their own narrowly scoped role addresses both problems the pipeline had with ECR (R1 bootstrap order, and permissions found late).

**Alternatives considered**:

- **Public GHCR**: fewer moving parts (no repositories, push role or pull permissions) and free. It was the earlier recommendation, set aside for consistency with the pipeline.
- **ECR in the instance stack**: this is exactly the pipeline's R1 problem.
- **One account-wide set of repositories shared by all environments**: it would need an account-level owner, which this repo deliberately doesn't have (R1).

**Adds**: two ECR repositories per env (base stack), one `release` role per env, the secret `AWS_ROLE_RELEASE_<ENV>`, the variable `RELEASE_ENVIRONMENTS`, ECR pull rights on the instance role, one host package (the credential helper), about $0.25 per month of storage, and a one-time GitHub ruleset that limits who can create `v*` tags. Because a tag push can now reach AWS, that ruleset becomes a security control rather than tidiness.

**Risk**: a new environment must be listed in `RELEASE_ENVIRONMENTS` *before* the release it deploys is tagged. Otherwise its repositories are empty. Preflight reports "release vX.Y.Z is not in this environment's registry", and the fix is to re-run `release.yml` for that tag. It skips images that already exist, so re-running is safe.

## R6. HTTPS on an IP address with a per-environment root

**Decision**: Caddy's built-in local CA (`tls internal`) is given a **per-environment root certificate and key**, so Caddy issues and renews short-lived leaf certificates for the instance's IP address (IP SAN) by itself.

- **Root**: an EC P-256 key with a self-signed certificate valid for 5 years, `CN=cloud-pricing-app <env> root`. It is created **once** by `app up` on the first deployment (with `openssl` on the machine running the command) and stored in SSM Parameter Store:
  - `/cloud-pricing-app/<env>/tls/root-key` as a SecureString with the AWS-managed key, which is free
  - `/cloud-pricing-app/<env>/tls/root-cert` as a String
- **At boot**: an init container (`ops fetch-tls`) writes both to a tmpfs volume that only Caddy reads.
- **If missing**: when the root is missing on an environment that already has backups, "up" stops and asks for `--new-root`, so a root the owner's devices trust is never silently replaced.
- **Getting it onto devices**: `app cert <env>` prints or saves the public root. The runbook covers macOS (Keychain → Always Trust), iOS (install the profile, then Settings → General → About → Certificate Trust Settings) and Android (user CA, which Chrome honors).
- **Ports**: only 443 is open. Port 80 is **not** opened, so plain HTTP is refused (Story 6 AS3) with no redirect rule to maintain.

**Rationale**: No public certificate authority can validate an IP-only, allowlisted host without opening it to the internet. Caddy already implements an internal CA, leaf rotation and IP SANs, so the only new piece is persisting the root.

**Alternatives considered**:

- Creating the root with OpenTofu's `tls` provider: the private key would sit in plain text in state, which FR-041 asks to avoid where possible.
- A new self-signed leaf every bring-up: devices would need to re-trust every time.
- Plain HTTP: rejected in clarification.

**Adds**: two SSM parameters per env, one init container, and the `cert` subcommand.

## R7. Pricing data: manifest reader, sources and cache

**Decision**: A new `pricing_data/manifest_source` layer replaces directory scanning.

- **Setting**: `PRICING_DATA_URI`, one value: `file:///abs/path`, a plain absolute path, or `s3://bucket[/prefix]`. The provider folder (`aws/`) is appended by the reader (FR-015). `AWS_PRICING_PARQUET_DIR` is removed, and if it is still set, startup stops naming its replacement (FR-004).
- **Storage adapter** (two small classes):
  - `get(key) -> bytes | None` treats `NoSuchKey`, `AccessDenied` and 404 alike as `None` (FR-008).
  - `list_dates(prefix)` lists manifest dates with a delimiter.
  - `download(key, dest)` (S3 only).
- **Selection** (pure function, test-first):
  1. Read `latest.json`, or `manifests/<pin>/manifest.json` when `ACTIVE_SNAPSHOT_DATE` is set.
  2. Validate the manifest with a Pydantic model mirroring `manifest.schema.json`.
  3. Accept it only if `manifest_version` major is `1`, every table `schema_version` is in a supported set (initially `{1}`), `status == "succeeded"`, and for the pointer, `snapshot_date` matches and `revision >= pointer.revision`.
  4. Validate every file path against the contract's regex, require that the date in the path equals the snapshot date, and reject `..`, absolute paths and backslashes. One bad path rejects the whole manifest before any I/O (FR-007).
- **Local source**: files are used in place under `<root>/<path>`, with no copy and no checksum pass (spec assumption).
- **S3 source**:
  1. Copy into `PRICING_CACHE_DIR/<provider>/<date>-r<revision>.tmp-<random>/`, preserving each file's manifest path.
  2. Verify `bytes` and `sha256` while streaming.
  3. Write `cache-entry.json` (manifest copy plus `verified_at`).
  4. Do one atomic `rename()` to `<date>-r<revision>/` (FR-009).

  A complete directory with `cache-entry.json` counts as verified and is never fetched again, including after a restart (FR-010). Leftover `*.tmp-*` directories are deleted at startup.
- **Grace re-read**: if a download takes longer than 5 minutes, the pipeline's default `SUPERSEDED_FILE_GRACE_MINUTES`, the manifest is re-read and the fetch restarts if its revision changed. A 404 on a listed file triggers the same restart (spec Edge Cases).
- **Active snapshot object**: immutable. It holds `(provider, date, revision, manifest, base_dir)` and has `files(table, region) -> list[str]` and `regions(table)`. Every pricing call takes the object once at the start of a request and passes it down, so a switch mid-request can't mix data. `pricing.py`, `catalog.py`, `regions.py` and `icon_coverage.py` call `files()` instead of building `part-0.parquet` paths. DuckDB's `read_parquet([...])` takes the list.
- **Cache clean-up (FR-011)** runs after each check. It keeps the active entry, plus `PRICING_CACHE_KEEP` others (default 1), within `PRICING_CACHE_MAX_BYTES` (default 1 GiB). A superseded entry is never deleted by the check that superseded it, only by a later one, and only when it is excess (beyond the keep count, over the size limit, or purged). Checks are serialized and requests take seconds, so this "grace instead of reference counting" rule guarantees nothing being read is deleted, without lock bookkeeping. If a new snapshot alone would exceed the limit, it isn't activated, and the reason is reported.
- **Latest pipeline run** (Admin tab): the newest dated `manifests/<D>/manifest.json`, whatever its status. It is found with one delimiter list on `aws/manifests/`, which the read policy allows.
- **Manual check**: `POST /api/v1/admin/pricing-snapshot/check` runs the same serialized check (FR-012).

**Rationale**: The design follows the producer's consumer rules one for one, keeps all selection logic in pure functions that can be tested without S3, and supports historical reads later (FR-016) because snapshots are first-class keyed objects.

**Alternatives considered**:

- Reading S3 directly through DuckDB `httpfs`: no checksum verification, a network trip on every query, and credentials inside DuckDB.
- Reference-counted cache entries: more state for no practical gain.
- Keeping `_SUCCESS` support: rejected in clarification.

**Adds**: settings `PRICING_DATA_URI`, `PRICING_CACHE_DIR`, `PRICING_CACHE_MAX_BYTES` and `PRICING_CACHE_KEEP`; the `boto3` dependency; one admin endpoint. `ACTIVE_SNAPSHOT_DATE` and `SNAPSHOT_CHECK_INTERVAL_SECONDS` are kept.

## R8. Database start-up: restore or initialize, then migrate

**Decision**: A one-shot Compose service `db-init` (backend image, `python -m src.ops db-init`) runs after Postgres is healthy and before the backend starts:

1. **If the database already has an `alembic_version` table** (the local packaged stack keeps its volume), skip to step 4.
2. Otherwise, find the backup to use: `--backup <id>` (passed by `app up --backup`), else the newest backup whose metadata says `verified: true`.
3. **Restore** with `pg_restore --no-owner --exit-on-error` into the empty database, then verify per-table row counts against the metadata (FR-022).
   - Any mismatch, or a checksum failure on download, stops the bring-up and names the backup. It never falls through to an empty database.
   - If the backup's Alembic revision is unknown to this release's migration scripts, it stops with "backup is from a newer release" (spec Edge Cases).
4. Run `alembic upgrade head`. Seeds are already idempotent migrations (`0004` Admin, `0005` standard architectures).
5. **Fresh database only**: set the default `Admin` account's password from SSM `/cloud-pricing-app/<env>/owner-password`. This replaces the `admin123` hash that migration `0004` writes. A restored database is never touched (FR-024).
6. Write `/run/app/db-init.json` with the result (`restored|fresh|existing`, backup id, row counts) for the health report.

The **Postgres password** is random per bring-up, generated by cloud-init and written to a root-only file read by Compose. It is never stored anywhere, because the data moves between bring-ups only through `pg_dump`, which carries no role passwords.

**Rationale**: Every bring-up exercises restore, migration and seed (spec goal 3). The order is the same on the laptop and in the cloud. Migrations are already the seeding mechanism.

**Alternatives considered**: Restore logic in a host shell script (not testable, so it conflicts with constitution V's Postgres read/write rule). A stored database password secret (an extra secret for no benefit).

**Adds**: one SSM SecureString (`owner-password`), the `db-init` service, and the `ops` CLI module.

## R9. Backups

**Decision**: `python -m src.ops backup --kind scheduled|teardown|manual` in the backend image:

1. Run `pg_dump -Fc` to a temp file, record its `sha256` and byte count, and run `pg_restore --list` on it, which must succeed.
2. Record per-table row counts for the user-data tables in the same transaction snapshot (`pg_dump --snapshot` with an exported snapshot).
3. Upload `<id>.dump`, then `<id>.json`, where the metadata is written last and marks the backup complete. The location is `BACKUP_URI`, either `s3://<backup-bucket>/<env>/db/` or `file:///…`.
4. Re-read the uploaded object's size and checksum, using S3's `ChecksumSHA256` on put, and set `verified: true` in the metadata.
5. Retention: keep the newest `BACKUP_KEEP` (default 14) verified backups, and never delete the newest verified one (FR-026). Older ones are deleted only after a new backup has been verified.

The backup id is `<UTC yyyymmddThhmmssZ>-<kind>-<release>`. Teardown runs it with `--kind teardown` after stopping `web` and `backend`, so nothing is being written (FR-031).

**`postgresql-client-18`** comes from the PGDG apt repository in the backend Dockerfile, with the signing key pinned by fingerprint, because Debian's own client is older than the Postgres 18 server and `pg_dump` must be at least the server version.

**Rationale**: `pg_dump` custom format is the standard portable logical backup, and restore verification by row counts is cheap and meaningful for this data size. The same command works against a laptop database, so the owner can seed the cloud from local data (see quickstart).

**Alternatives considered**: EBS snapshots, which tie data to AWS volumes and can't restore to a laptop. S3 lifecycle retention, which is age-based and can't express "keep the newest N and never the last verified".

**Adds**: settings `BACKUP_URI` and `BACKUP_KEEP`, one apt repository in the Dockerfile, and the backup bucket (base stack, private, SSE-S3, versioning off, abort-incomplete-multipart rule).

## R10. On-instance timers, alerts and logs

**Decision**:

- **Scheduled backup**: a systemd timer (`OnUnitActiveSec=6h`, `Persistent=true`) runs `docker compose run --rm ops backup --kind scheduled`. On failure, the ops command publishes to the env's SNS topic (FR-044).
- **Forgotten instance**: a systemd timer every 30 minutes runs `ops uptime-alert`. When uptime passes `UPTIME_ALERT_HOURS` (default 12), it publishes and records the time in `/var/lib/app/last-uptime-alert`, then repeats every `UPTIME_ALERT_REPEAT_HOURS` (default 12). Alert only (clarification), and SC-012 is met by the 30-minute cadence.
- **Address notification**: when "up" finishes, it publishes `"<env> is up at https://<ip> (release vX.Y.Z)"` to the same topic. This is how the owner gets the address on a phone without it appearing in public workflow logs (R13).
- **Logs**: Docker's `awslogs` driver sends every container's output to `/cloud-pricing-app/<env>` (base stack, retention `LOG_RETENTION_DAYS` = 14). The JSON logs from feature 017 arrive as-is. Timer and ops-command output goes to the same group through the `ops` container.

**Rationale**: Running the checks on the instance needs no extra AWS services. The cost being protected against *is* the running instance, so an on-instance check is present exactly when it's needed.

**Alternatives considered**:

- A scheduled Lambda watchdog, as in the pipeline repo: it catches a wedged instance too, but adds a function, a schedule, IAM, packaging and tests. The account budget's forecast alert already backstops cost.
- CloudWatch alarms: they can't express "running longer than N hours" without a custom metric.

**Adds**: two timers, one SNS topic with an email subscription (a one-time confirmation click), settings `UPTIME_ALERT_HOURS` and `UPTIME_ALERT_REPEAT_HOURS`, and one log group.

## R11. The `app` command and the workflows: one code path

**Decision**: One script, `deploy/app` (bash, `set -euo pipefail`, shellcheck-clean), with subcommands `up`, `down`, `status`, `allow add|remove|list`, `cert` and `ami-latest`. It takes its **environment and region from explicit arguments or environment variables** (`APP_ENV`, `AWS_REGION`), never from the machine's AWS config files (FR-048).

- **From the laptop**: the owner runs it with their own AWS profile.
- **From GitHub**: one workflow, `app.yml` (`workflow_dispatch`: `action`, `environment`, `release`, `backup`, `address`), runs the same script with the `deploy` role. Both paths give the same result by construction (FR-027).

`up` steps, each checking its real outcome (FR-047):

1. **Preflight** (`aws sts get-caller-identity`; the base stack's outputs exist; the allowlist parameter is readable; the release images exist). It fails with the missing item named.
2. **Take the operation lock**: `s3api put-object --if-none-match '*'` on `locks/<env>.json` in the backup bucket, with owner, action, start time and run URL. A lock older than 2 hours can be broken with `--break-lock` (FR-030). GitHub's `concurrency: app-<env>` also queues hosted runs.
3. Resolve the release and digests (R5).
4. Make sure the TLS root exists (R6).
5. `tofu apply` on the instance stack, with the release digests, AMI and instance type.
6. **Wait for health through SSM**, not HTTP. The runner's IP isn't on the allowlist, so it can't reach the app. `aws ssm send-command` runs `ops health --wait 600`, which waits for `db-init` to succeed and the backend's `/health` to answer, does a login check, and returns JSON (`db: restored|fresh`, `pricing: ok|unavailable + reason`, release). The script polls `get-command-invocation` until it reaches a terminal status, and anything other than `Success` fails (FR-047).
7. Publish the address (R10). Print it locally, and mask it in GitHub.
8. Release the lock in a `trap`, so it's released on every exit path.

`down`:

1. Lock.
2. If the instance exists, SSM: `compose stop web backend`, then `ops backup --kind teardown`, which must return `verified: true`. Otherwise stop and destroy nothing. `--force-without-backup` is the named override (FR-031).
3. `tofu destroy` on the instance stack.
4. Confirm no tagged instance remains.
5. Unlock.

If the instance stack has no instance, `down` succeeds (Story 3 AS5).

**Redeploying a different release while up**: the instance's user-data contains the release digests, and the instance uses `user_data_replace_on_change = true`. A release change therefore replaces the instance. Before applying, `up` runs the same SSM backup as `down` (`--kind redeploy`, which must be verified), and the new instance restores from it. A release change is not the only thing that replaces the instance: a new `ami_id` or a different `db_init_args` does too. So `up` decides from the saved plan, not from the release tag: if the plan replaces or destroys a running `aws_instance`, the `redeploy` backup runs first (FR-029). `allow` uses the running instance's values and refuses to apply a plan that would replace it. An `up` whose plan leaves the instance alone is an apply plus a health check. One deployment path, and every release change exercises restore (spec goal 3). An in-place `compose pull` upgrade would be faster but would be a second path to test.

**Rationale**:

- One script means one place to test and document.
- SSM is already needed for keyless shell access, so health checks and backups add no new channel.
- Bash plus the AWS CLI is what the runners and the laptop already have.
- The steps are thin glue. All the logic that needs tests (restore, verify, retention, health) lives in Python inside the image.

**Alternatives considered**:

- The local command dispatching the GitHub workflow: needs `gh`, which isn't installed, and GitHub to be up.
- Separate workflows per action: more files with the same steps.
- Python for the orchestration script: would need a Python environment on the runner and laptop just for AWS glue.

**Adds**: one script, one workflow, one lock object, and laptop prerequisites (`aws` CLI v2, `tofu`, `openssl`, `jq`), checked by preflight.

## R12. Allowlist storage and updates

**Decision**: The allowlist is one SSM `StringList` parameter, `/cloud-pricing-app/<env>/allowlist`. It is created by the base stack with `lifecycle { ignore_changes = [value] }` and seeded from a base-stack variable.

- The instance stack reads it with a data source and renders one security-group ingress rule per address on 443.
- `app allow add|remove <ip>` validates the input (a single IPv4 or IPv6 address, written as `/32` or `/128`), updates the parameter, prints the full list (FR-036), and runs `up`'s apply step only if the instance exists. That is a quick `tofu apply` whose only diff is the security-group rules, and it takes the same lock.
- Changes survive down/up cycles because the parameter is in the base stack (Story 6 AS7).

**Rationale**: There is one source of truth that both the laptop and GitHub can edit, and it is not committed to a public repo.

**Alternatives considered**:

- A committed tfvars list: the home IP would be public in the repo.
- A GitHub secret: the laptop can't read it, so there would be two sources of truth.

**Adds**: one SSM parameter per env.

## R13. Public-repo hygiene for workflow logs

**Decision**:

- Role ARNs are secrets, and AWS logins mask the account ID.
- The app's address and any `address` input are masked with `::add-mask::` as the first step of the job.
- The address reaches the owner through the alert email (R10) and `app status` locally.
- **Open verification task**: confirm whether `workflow_dispatch` input values are visible to anonymous viewers of a public repo's run pages or API. If they are, the runbook says to make allowlist changes from the laptop, or accept the exposure. An IP address alone doesn't grant access past the allowlist and HTTPS.

**Adds**: no configuration, only steps inside the workflow.

## R14. Infrastructure tests, pinning and CI

**Decision**:

- **`tofu test`** with mocked providers for `base` and `instance`, run on every PR with no cloud access (FR-052), asserting:
  - the instance stack contains no bucket, parameter, log group or topic (nothing long-lived)
  - the base stack has no EC2 or VPC resources
  - the ECR repositories are in the base stack, `IMMUTABLE`, scan-on-push, with the lifecycle rule and `force_delete = false`
  - the `release` role can only push to the env's two repositories
  - ingress is exactly 443 from the allowlist, and nothing else is open (22 in particular)
  - IMDSv2 is required
  - the root volume is encrypted and deleted on termination
  - the deploy role's statements are limited to tag- or name-scoped resources, apart from listed `*`-only actions
  - the trust subjects are exact
- **PR plan** of the instance stack with the `plan` role, posted as a comment and switched on by the variable `AWS_PLAN_ENABLED`, as in the pipeline repo.
- **Pinning (FR-053)**:
  - GitHub Actions are pinned to full commit SHAs, with the version in a comment.
  - OpenTofu `1.10.6`, the same as the pipeline repo.
  - The AWS provider is locked with `.terraform.lock.hcl` hashes for `linux_arm64`, `linux_amd64` and `darwin_arm64` (`tofu providers lock -platform=…`).
  - Base images are pinned by digest (`python:3.12-slim-bookworm`, `postgres:18`, `caddy:2`, `node:20` for the build stage).
  - `uv.lock` and `package-lock.json` already exist.
  - The existing `ci.yml` is moved to the same pins (it uses floating `@v4`/`@v3` tags and `ubuntu-latest`).
- **Docker build check**: `ci.yml` builds both images for arm64 without pushing.
- **shellcheck** on `deploy/app`.

**Adds**: tests and lock files; no runtime configuration.

## R15. Local development and the local packaged stack

**Decision**:

- **Non-packaged dev** is unchanged except for the setting: `PRICING_DATA_URI=file:///…/DATA/pipeline`. The developer creates that root once from the legacy data with the pipeline's own command, run from the data-retrieval repo:

  ```
  PIPELINE_STORAGE_URI=file:///…/DATA/pipeline upload-history --snapshot-date <D> --source …/DATA
  ```

  Or they point at S3 through the pipeline's documented off-AWS reader role.
- **Test fixture**: `backend/tests/fixtures/pricing_parquet/` is rebuilt in the new layout (`aws/parquet/…`, `aws/manifests/<D>/manifest.json`, `aws/manifests/latest.json`) by an updated `build_test_pricing_fixture.py`, which writes real sha256 and row counts. CI sets `PRICING_DATA_URI` to it. A small set of hand-written manifest fixtures (partial, failed, purged, bad path, unsupported version, revision regress) covers the selection rules.
- **Contract copies**: `latest.schema.json` and `manifest.schema.json` are vendored into `backend/tests/fixtures/contracts/`, with the source repo commit, and validated against in tests through the `jsonschema` dev dependency. The Pydantic models are checked against the schemas' own `examples`.
- **Local packaged stack (Story 8)**: `compose.yaml` plus `compose.local.yaml`:
  - builds the images locally
  - bind-mounts the local data root read-only
  - `BACKUP_URI=file:///backups`, a bind-mounted directory
  - publishes Caddy on `https://localhost:8443` with a laptop root from `app cert local --create`
  - no SNS (alerts are logged only)
  - a named volume for Postgres

  Docker is a prerequisite (Docker Desktop or Colima) and is not installed today.

**Adds**: one Compose override file and one dev dependency (`jsonschema`).

## R16. Admin tab changes

**Decision**: `GET /api/v1/admin/system-info` changes shape (see [contracts/admin-api.md](./contracts/admin-api.md)):

- **Removed**: `waiting_snapshots` and the `pinned_incomplete` issue kind. A pin must now be `succeeded`.
- **Added**:
  - `source` (kind and display location, never credentials)
  - `active` (date, revision, run id, pipeline version, created at, regions succeeded and failed)
  - `latest_run` (date, revision, status, failed regions with reasons)
  - `cache` (entries, states, sizes, total and limit)
  - `deployment` (release and environment, from settings, so the owner can see which release is live)
- **Kept**: `missing_regions`, now computed from the manifest's `regions.failed`. The frontend `SystemInformationSection` is updated and types are regenerated (constitution IV).

**Adds**: the `APP_RELEASE` and `APP_ENVIRONMENT` settings, which are informational and set by cloud-init.

## R17. Security posture of the existing auth (risk, not in scope)

**Finding**:

- The bearer token is the user's UUID and never expires.
- Unknown UUIDs create guest users.
- Named accounts without a password are claimed by the first login.

On a laptop that is harmless. On an internet-reachable host it means anyone who can reach the API can create guests, and anyone who learns a user's UUID is that user.

**Decision for this feature**:

- The allowlist and HTTPS are the controls, as the spec states ("multi-user hardening out of scope").
- The default Admin's password comes from a secret on a fresh database (R8), and `admin123` never reaches the cloud.
- The runbook says to set passwords on every named account before first cloud use.

**Recommendation**: a follow-up feature for signed, expiring session tokens. That is called out to the owner rather than added here (FR-058: it would be a significant change to auth, not to deployment).
