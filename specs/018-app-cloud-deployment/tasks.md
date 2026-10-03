---

description: "Task list for 018-app-cloud-deployment"
---

# Tasks: On-Demand Cloud Deployment with Manifest-Driven Pricing Data

**Input**: Design documents from `specs/018-app-cloud-deployment/`: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md).

**Tests**: Required. Constitution V makes tests-first mandatory for pricing logic, DuckDB queries and Postgres read/write of user data. FR-052 requires infrastructure tests. Each test task must be written and **seen failing** before its implementation task.

**Organization**: Tasks are grouped by user story (spec.md), in the spec's priority order. Paths are relative to the repository root.

**Conventions for every task**:

- Backend commands run from `backend/` with `uv run …`.
- New Python modules follow the existing style: module docstring citing `018-app-cloud-deployment` and the FR numbers, structlog via `src.logging_config.get_logger`, and settings via `src.config.settings`.
- No task may hard-code an AWS account ID, a personal IP address or a secret.
- Infrastructure uses OpenTofu `1.10.6` and AWS provider `~> 6.0`. Every resource carries the tags `app = "cloud-pricing-app"` and `environment = var.environment`.
- GitHub Actions are pinned to full commit SHAs with the version in a trailing comment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to (US1–US8)

---

## Phase 1: Setup (shared infrastructure)

**Purpose**: dependencies, folders, pinned tool versions and test fixtures that every later phase uses.

- [X] T001 Add `boto3` to `[project].dependencies` and `jsonschema` to the `dev` extra in `backend/pyproject.toml`, then run `uv lock` to update `backend/uv.lock`. Add `boto3-stubs` only if `ruff` or tests need it (they shouldn't).
- [X] T002 [P] Create the empty deployment folder layout with a one-line `README.md` in each: `infra/base/`, `infra/instance/`, `infra/envs/`, `deploy/`, `deploy/host/`. Add `infra/**/.terraform/`, `*.tfstate*`, `.local-backups/` and `.local-tls/` to `.gitignore`.
- [X] T003 [P] Vendor the pipeline's contracts into `backend/tests/fixtures/contracts/`: copy `latest.schema.json`, `manifest.schema.json` and `storage-layout.md` from `../cloud-pricing-data-retrieval/specs/003-pipeline-cloud-deployment/contracts/`. Add `backend/tests/fixtures/contracts/SOURCE.md` recording the source repo, path and commit (`git -C ../cloud-pricing-data-retrieval rev-parse HEAD`), and saying the files must be re-copied, not edited, when the contract changes.
- [X] T004 Rewrite `backend/scripts/build_test_pricing_fixture.py` to write the **new layout** to `backend/tests/fixtures/pricing_parquet/` (the default output stays the same folder):
  - **Data files**: `aws/parquet/<table>/snapshot_date=<D>/region=<R>/part-<run_id>.parquet`, using a fixed `run_id` such as `20260924T000000Z-f1x7ur`.
  - **Manifest**: `aws/manifests/<D>/manifest.json`, valid against the vendored `manifest.schema.json`, with `status: "succeeded"`, `revision: 1`, `origin: "backfill"`, real `bytes`/`sha256`/`row_count` per file and per table, and every table `schema_version: 1`.
  - **Pointer**: `aws/manifests/latest.json`.
  - **Source**: either a legacy tree (`--source …/DATA/pricing_aws/parquet`, as today) or a new-layout root (`--source-uri file:///…/DATA/pipeline`).
  - **Keep**: the existing SKU selection rules (SEED_SKUS plus standard-architecture SKUs, verbatim rows, source order).
  - Update the module docstring.
- [X] T005 Regenerate the fixture with the rewritten script. Delete the old `backend/tests/fixtures/pricing_parquet/<table>/` folders, commit the new `aws/` tree, and confirm `latest.json` and the manifest validate against the vendored schemas with a one-off `jsonschema` check.
- [X] T006 [P] Rewrite `backend/tests/helpers/parquet_tree.py` as `make_pipeline_root(root, snapshots)`. It builds a new-layout root (data files, `manifests/<D>/manifest.json`, optional `latest.json`) from a compact spec per snapshot: `date`, `revision`, `status`, `regions`, `failed_regions`, `services` (written to `service_dim`), `schema_versions`, `extra_files` (to simulate leftover superseded files), `bad_paths`, and `point_latest` (bool). It computes real sha256 and byte sizes. Keep `make_snapshot_tree` only until T096 removes it.
- [X] T007 [P] Create hand-written edge-case manifests in `backend/tests/fixtures/manifests/`, each a full valid-shape JSON document:
  - `partial.json`, `failed.json`, `purged.json`
  - `bad_path_dotdot.json`, `bad_path_absolute.json`, `bad_path_other_date.json`, `bad_path_other_region.json`
  - `unsupported_major.json` (`manifest_version: "2.0"`), `unsupported_schema.json` (a table with `schema_version: 2`)
  - `minor_bump_extra_field.json` (`manifest_version: "1.1"` with an unknown optional field)

**Checkpoint**: dependencies installed. The fixture and helpers exist in the new layout. Existing tests now fail because the app still reads the old layout, and that is expected until Phase 3.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: everything at least two stories need. This covers settings, the storage adapters, the backup and restore core, packaging, the base stack and the `deploy/app` skeleton.

**⚠️ CRITICAL**: no user-story phase starts before this phase is complete.

### Settings and storage

- [X] T008 Write failing tests in `backend/tests/unit/test_config_data_source.py`:
  - `PRICING_DATA_URI` accepts `file:///abs`, `/abs` and `s3://bucket[/prefix]`, and rejects relative paths, `http://` and empty values, each with a message naming the setting.
  - A `file://` path that doesn't exist stops startup.
  - Setting `AWS_PRICING_PARQUET_DIR` stops startup with the exact message in [contracts/configuration.md](./contracts/configuration.md).
  - Defaults and bounds hold for `PRICING_CACHE_DIR`, `PRICING_CACHE_MAX_BYTES` (≥ 268435456), `PRICING_CACHE_KEEP` (≥ 0), `DUCKDB_MEMORY_LIMIT`, `DUCKDB_THREADS` (≥ 1), `BACKUP_URI` (`file://` or `s3://` only), `BACKUP_KEEP` (≥ 1), `UPTIME_ALERT_HOURS`, `UPTIME_ALERT_REPEAT_HOURS`, `APP_ENVIRONMENT` and `APP_RELEASE`.
- [X] T009 Implement the settings in `backend/src/config.py`:
  - Remove `aws_pricing_parquet_dir`.
  - Add a `model_validator(mode="before")` that raises if `AWS_PRICING_PARQUET_DIR` is present in the environment or `.env`.
  - Add the new fields from [contracts/configuration.md](./contracts/configuration.md), and a parsed `pricing_data_source` property returning `(kind, root)`.
  - Keep every existing setting.
  - Make T008 pass.
- [X] T010 [P] Write failing tests in `backend/tests/unit/test_storage.py` for `src/pricing_data/storage.py`:
  - `LocalStore`: `get` returns bytes or `None` for a missing key; `list_manifest_dates` returns sorted dates from `aws/manifests/` folders and ignores `latest.json` and non-date names; `file_path` stays inside the root.
  - `S3Store`, against an in-memory fake client (a small class in `backend/tests/helpers/fake_s3.py`, also created in this task, implementing `get_object`, `head_object`, `list_objects_v2` with `Delimiter`, `put_object` with `IfNoneMatch`, `delete_object`, `download_fileobj` and the `ChecksumSHA256` fields): `get` maps `NoSuchKey`, `AccessDenied` and 404 `ClientError` to `None` (FR-008) and re-raises other errors; `download` streams to a destination while computing sha256 and fails on a size or hash mismatch.
- [X] T011 Implement `backend/src/pricing_data/storage.py`:
  - `LocalStore(root)` and `S3Store(bucket, prefix, client=None)`, both providing `get(key)`, `list_manifest_dates(provider)` and `exists(key)`; `LocalStore.file_path(key)`; `S3Store.download(key, dest, expected_bytes, expected_sha256)`.
  - `S3Store` builds its client lazily with `boto3.client("s3", config=Config(retries={"mode": "standard"}))`, using the default credential chain and never a profile setting.
  - Add `open_store(settings)` to build the store from `pricing_data_source`.
  - Make T010 pass.

### Database lifecycle core (US2, US3, US4, US7, US8 all use it)

- [X] T012 [P] Write failing tests in `backend/tests/unit/test_backup_store.py` for `src/ops/backup_store.py`, with `file://` in `tmp_path` and `s3://` through the fake S3:
  - ids follow `<yyyymmddThhmmssZ>-<kind>-<release>`
  - `put_backup` writes `.dump` before `.json`
  - `list_backups` ignores a `.dump` without its `.json`
  - `newest_verified()` and `get(id)`
- [X] T013 [P] Write failing tests in `backend/tests/unit/test_backup_retention.py` for the pure function `select_deletions(backups, keep, now)`:
  - keeps the newest `keep` verified backups
  - never deletes the newest verified backup, even with `keep=1` and a newer unverified one present
  - deletes incomplete backups older than 24 h only
  - returns ids, deleting nothing itself
- [X] T014 Implement `backend/src/ops/backup_store.py` (file and S3 backends, using `storage.py` helpers where they fit) and the retention function in `backend/src/ops/backup.py`. Make T012 and T013 pass.
- [X] T015 Write failing integration tests in `backend/tests/integration/test_backup_roundtrip.py`, against the test Postgres (`TEST_DATABASE_URL`) with `pg_dump` and `pg_restore` on `PATH`:
  - `backup --kind manual` to a `file://` location produces metadata with `alembic_revision`, `row_counts` for every ORM table (from `Base.metadata`, not a hard-coded list), sha256, bytes and `verified: true`.
  - Restoring into an empty database reproduces the same row counts.
  - A corrupted `.dump` (one flipped byte) fails verification with exit code 4.
  - Retention runs only after a verified backup.
  - Skip with a clear reason if `pg_dump` is missing locally. CI must have it (T088).
- [X] T016 Implement `backend/src/ops/backup.py`:
  1. `pg_dump -Fc` with an exported snapshot (`--snapshot`, taken in the same transaction as the row counts) to a temp file.
  2. `pg_restore --list` check.
  3. Upload the dump, then the metadata.
  4. Re-read the size and sha256 (S3 `ChecksumSHA256` on put plus `head_object`), and set `verified: true`.
  5. Apply retention.
  6. On any failure, call `alerts.notify` and exit `4`.

  Make T015 pass.
- [X] T017 Write failing integration tests in `backend/tests/integration/test_db_init_restore.py` for `src/ops/db_init.py`:
  - **Empty database, no backups**: `fresh`. Migrated to head. The default Admin's password is replaced from a stubbed parameter reader (`admin123` no longer verifies, and the stub password does).
  - **Empty database with backups**: `restored`, from the newest verified one, with row counts verified.
  - **`--backup <id>`**: restores that one.
  - **Row-count mismatch**: exit 4, and the database is not left half-initialized (the bring-up stops).
  - **Unknown `alembic_revision`**: exit 3, "backup is from a newer release".
  - **Existing database** (an `alembic_version` table is present): `existing`, migrations applied, Admin password untouched.
  - **Fresh database with no owner password configured**: exit 3 unless `--allow-default-admin-password`.
- [X] T018 Implement `backend/src/ops/db_init.py` per [contracts/ops-cli.md](./contracts/ops-cli.md):
  - Detect the state, restore with `pg_restore --no-owner --exit-on-error`, verify the counts, run `alembic upgrade head` programmatically (`alembic.command.upgrade` with `backend/alembic.ini`), then on a fresh database set the password with `auth_service.hash_password`.
  - Seed data comes only from the Alembic migrations (`0004` Admin, `0005` standard architectures), which already insert with `WHERE NOT EXISTS`. `alembic upgrade head` therefore covers FR-021's "apply seed data, safe to repeat". Don't add a separate seeding step.
  - Read the owner password through `src/ops/params.py`, a new small module wrapping `ssm.get_parameter(WithDecryption=True)`, so tests can stub it.
  - Write `/run/app/db-init.json`, with the path overridable for tests.

  Make T017 pass.
- [X] T019 [P] Implement `backend/src/ops/alerts.py` (`notify(message, subject)` publishes to `ALERT_TOPIC_ARN` through SNS, or only logs `alert not sent: no topic` when unset; it never raises) and its unit test `backend/tests/unit/test_alerts.py` (stubbed client, and the unset-topic path).
- [X] T020 Implement the CLI entry `backend/src/ops/__main__.py` (argparse subcommands `db-init`, `backup`, `backups list`, `notify`). Each command logs JSON, prints exactly one JSON result object as the **last stdout line**, and exits with the contract's codes (0, 1, 3, 4). Add `backend/tests/unit/test_ops_cli.py`, which runs `python -m src.ops backups list` against a `file://` location and checks the last-line JSON and the exit code.

### Packaging

- [X] T021 [P] Create `backend/Dockerfile`:
  - Base: `python:3.12-slim-bookworm`, pinned by digest.
  - Install `postgresql-client-18` from the PGDG apt repository, with the signing key downloaded and checked against its published fingerprint in the Dockerfile (fail the build on mismatch).
  - Install `uv` (pinned version, copied from its official image by digest), `uv sync --frozen --no-dev`, copy `src/`, `alembic.ini` and `scripts/` needed at runtime.
  - Run as a non-root user `app`.
  - Default command: `uvicorn src.main:app --host 0.0.0.0 --port 8000`.
  - Labels: `org.opencontainers.image.revision` from build arg `GIT_SHA`, and `APP_RELEASE` from build arg `RELEASE`.

  Add `backend/.dockerignore` (`.venv`, `tests`, `__pycache__`, `*.log`).
- [X] T022 [P] Create `frontend/Dockerfile.web`: stage 1 `node:20` (pinned by digest) runs `npm ci && npm run build`; stage 2 `caddy:2` (pinned by digest) copies `dist/` to `/srv` and `frontend/Caddyfile` to `/etc/caddy/Caddyfile`. Add `frontend/.dockerignore`.
- [X] T023 [P] Create `frontend/Caddyfile`:
  - A global `pki { ca local { root { cert /tls/root.crt; key /tls/root.key } } }` block.
  - One site block for `https://{$PUBLIC_ADDRESS}:{$HTTPS_PORT:443}` with `tls internal`, `handle /api/* { reverse_proxy backend:8000 }`, `handle /health { reverse_proxy backend:8000 }`, and `handle { root * /srv; try_files {path} /index.html; file_server }`.
  - No HTTP listener (`auto_https disable_redirects`, and `http_port` unused).
  - JSON access logs to stdout.
- [X] T024 Create `compose.yaml` at the repository root with services:
  - `db`: `postgres:18` pinned by digest, `shared_buffers=128MB`, password from the `POSTGRES_PASSWORD_FILE` secret, a healthcheck with `pg_isready`, and a named volume.
  - `tls-init` (backend image): `python -m src.ops fetch-tls --out /tls`, with a tmpfs volume `tls`.
  - `db-init` (backend image): `python -m src.ops db-init ${DB_INIT_ARGS:-}`, depending on `db` healthy.
  - `backend`: depends on `db-init` with `service_completed_successfully`, mounts the cache volume at `/var/lib/app/pricing-cache`, with an HTTP healthcheck on `/health`.
  - `web`: depends on `tls-init` completed and `backend` healthy, publishes `${HTTPS_PORT:-443}:443`, and mounts `tls` read-only.
  - `ops` (backend image, profile `ops`): used by `docker compose run --rm ops …`.

  All images come from variables `BACKEND_IMAGE` and `WEB_IMAGE` (digests in the cloud). Every service gets its settings from `/opt/app/.env` through `env_file`. The `awslogs` logging driver is set through an `x-logging` anchor whose options come from variables (`LOG_GROUP`, `AWS_REGION`), so the local override can replace it.
- [X] T025 Add the `fetch-tls` subcommand in `backend/src/ops/tls.py` and wire it in `__main__.py`:
  - Read `/cloud-pricing-app/<env>/tls/root-key` (SecureString) and `/root-cert` through `params.py`, write them to `--out` with mode 0400, and print the fingerprint and `not_after`.
  - With `TLS_ROOT_DIR` set (local stack), copy from that directory instead.

  Unit test in `backend/tests/unit/test_tls_fetch.py` with a stubbed parameter reader and a throwaway openssl-generated cert.

### Base stack and `deploy/app` skeleton

- [X] T026 Look up and record the exact IAM actions and resource types needed, before writing any policy (FR-049, research R2, [contracts/infrastructure.md](./contracts/infrastructure.md) "Still to confirm"). Use the Service Authorization Reference (AWS MCP `search_documentation` or `read_documentation`) for EC2, SSM, ECR, S3, SNS, Logs and IAM PassRole. Write the result into a new section, "Verified action list", in `specs/018-app-cloud-deployment/contracts/infrastructure.md`. List, per action, the resource ARN pattern, whether it accepts only `*`, and the condition keys used. Include `ssm:GetCommandInvocation` and `ssm:ListCommandInvocations`, `ec2:DescribeImages`, `ecr:DescribeImages`, the `ec2:RunInstances` resource set (instance, volume, network-interface, image, subnet, security-group), and `ssm:SendCommand` with `ssm:resourceTag/…`.
- [X] T027 Create `infra/base/` (`versions.tf`, `providers.tf`, `variables.tf`, `main.tf`, `iam_ci.tf`, `iam_instance.tf`, `ecr.tf`, `outputs.tf`):
  - **Variables** (all validated): `environment` (`dev|qa|prod`), `aws_region`, `state_bucket_name`, `github_repository` (`grp3d/cloud-pricing-app`), `github_owner_id`, `github_repo_id`, `alert_email`, `data_bucket_name`, `data_read_policy_name`, `log_retention_days` (default 14), `backup_bucket_suffix`, `initial_allowlist` (list, default `[]`).
  - **Data sources**: `aws_iam_openid_connect_provider` by URL `https://token.actions.githubusercontent.com`, the state bucket, the data bucket and the data read policy. A missing item fails the plan in its lookup, before anything is created. Don't add `precondition` blocks for these, because they never run when the lookup fails (contracts/infrastructure.md). T067's runbook gives a check command for each item.
  - **Backup bucket** `cloud-pricing-app-backups-<env>-<suffix>`: public access blocked, SSE-S3, versioning off, a lifecycle rule aborting incomplete multipart uploads after 1 day, `force_destroy = false`.
  - **Log group** `/cloud-pricing-app/<env>`.
  - **SNS topic** `cloud-pricing-app-alerts-<env>` with an email subscription.
  - **SSM parameter** `/cloud-pricing-app/<env>/allowlist` (`StringList`, seeded from `initial_allowlist` or the placeholder `none`, with `lifecycle { ignore_changes = [value] }`).
  - **ECR repositories** `cloud-pricing-app-backend-<env>` and `cloud-pricing-app-web-<env>`: `IMMUTABLE`, `scan_on_push = true`, `force_delete = false`, and a lifecycle policy that keeps 5 tagged images and expires untagged ones after 1 day.
  - **Instance role and instance profile** `cloud-pricing-app-instance-<env>`, with:
    - the pipeline's data read policy attached by ARN
    - `AmazonSSMManagedInstanceCore`
    - inline statements for backup bucket read/write on `<env>/db/*`, SSM `GetParameter(s)` on `/cloud-pricing-app/<env>/*` plus `kms:Decrypt` through the `aws/ssm` key with the `kms:ViaService` condition, `sns:Publish` to the topic, logs `CreateLogStream` and `PutLogEvents` on the group, and ECR pull on the two repositories
  - **CI roles** `cloud-pricing-app-gha-{plan,release,deploy}-<env>` with trust and permissions exactly as in contracts/infrastructure.md and T026's verified list. Trust is `StringLike` on `token.actions.githubusercontent.com:sub` with the immutable subject prefix `repo:grp3d@<owner_id>/cloud-pricing-app@<repo_id>`, and `StringEquals` on `aud = sts.amazonaws.com`.
  - **Outputs**: role ARNs, `gha_trust_subjects`, the backup bucket, the topic ARN, the log group, the repository URLs, the instance profile name and the allowlist parameter name.
  - **Backend**: `backend "s3" {}` with a comment showing `tofu init -backend-config=../envs/<env>.backend.hcl -backend-config="key=app/<env>/base.tfstate"`.
- [X] T028 Write `infra/base/tests/base.tftest.hcl` (mocked AWS provider, `command = plan`) asserting contracts/infrastructure.md tests 4, 5 and 6:
  - no `aws_instance` or `aws_vpc` resources
  - the bucket blocks public access and is encrypted
  - both repositories are IMMUTABLE, scan on push, have the lifecycle rule and `force_delete = false`
  - exact trust subjects for plan, release and deploy
  - every deploy statement with `resources = ["*"]` is in the approved list or carries a tag condition
  - the release role's only non-`*` resources are the two repositories

  Run `tofu test` in `infra/base`.
- [X] T029 [P] Create `infra/envs/prod.tfvars` (environment, region `us-east-1`, `instance_type = "t4g.small"`, `root_volume_gib = 20`, `data_bucket_name = "cloud-pricing-data-prod-g08a9i"`, `data_read_policy_name = "cloud-pricing-data-read-prod"`, `log_retention_days = 14`, `backup_bucket_suffix` chosen by the owner with no account ID, and `ami_id` left as a placeholder comment to fill with `deploy/app ami-latest`), `infra/envs/prod.backend.hcl` (`bucket = "cloud-pricing-shared-tfstate-g08a9i"`, `region`, `encrypt = true`, `use_lockfile = true`, no key), plus `dev.tfvars.example` and `qa.tfvars.example`.
- [X] T030 Generate the provider lock file for `infra/base` with `tofu providers lock -platform=linux_arm64 -platform=linux_amd64 -platform=darwin_arm64` and commit `infra/base/.terraform.lock.hcl`. The `infra/instance` lock file is generated in T099, once that stack exists.
- [X] T031 Create `deploy/app` (bash, `#!/usr/bin/env bash`, `set -euo pipefail`, executable) with the shared skeleton:
  - **Argument parsing**: `--env` is required; `AWS_REGION` is required and never read from AWS config files (FR-048).
  - **`require_tools`**: `aws`, `tofu`, `jq` and `openssl`, each with a version check.
  - **`tf_init <stack>`**: `-backend-config=infra/envs/$ENV.backend.hcl -backend-config=key=app/$ENV/<stack>.tfstate`.
  - **`base_outputs`**: reads the base stack's outputs, and fails with exit 3 "run the one-time setup" if they are missing.
  - **`lock_acquire`/`lock_release`**: `s3api put-object --if-none-match '*'` on `locks/$ENV.json` with `{action, by, started_at, run_url}`; release in a `trap`; `--break-lock` only if older than 2 h; exit 3 naming the holder otherwise.
  - **`ssm_run <instance> <script>`**: `send-command` with `AWS-RunShellScript`, polls `get-command-invocation` until a terminal status, fails unless `Success`, prints the stderr tail, and returns the stdout's last JSON line.
  - **`mask`**: emits `::add-mask::` when `GITHUB_ACTIONS=true`.
  - **Exit codes**: as in [contracts/app-cli.md](./contracts/app-cli.md).
  - **`status`**: implemented here (instance state, address, uptime, release tag, last backup from `ops backups list` through SSM if running, or from S3 listing if down, and the lock holder). If the instance is running, also send the address notice with `ssm_run … ops notify`, because the address is masked in GitHub logs (FR-038). This uses the instance role's existing `sns:Publish`, so the `deploy` role needs no new permission.
- [X] T032 [P] Create `deploy/tests/app_test.sh`, a plain bash test runner with no network. It stubs `aws` and `tofu` with fake scripts on `PATH` that record their calls, and asserts:
  - a missing `--env` gives exit 2
  - a missing `AWS_REGION` gives exit 2 (even when `~/.aws/config` has a region)
  - a held lock gives exit 3 and names the holder
  - the lock is released on failure
  - `ssm_run` fails on `Failed`, `Cancelled` and `TimedOut`
  - masking lines are printed under `GITHUB_ACTIONS=true`
  - `status` with a running instance calls SSM `ops notify` with the address; with no instance it doesn't

**Checkpoint**: settings, storage, backup and restore, packaging, the base stack and the script skeleton are done. User stories can start.

---

## Phase 3: User Story 1 - The app reads pricing data through manifests, locally or from the cloud (Priority: P1) 🎯 MVP

**Goal**: replace directory and `_SUCCESS` scanning with manifest-driven reading from `PRICING_DATA_URI`, so that a local root works offline and an S3 root works through a verified cache.

**Independent test**: [quickstart.md](./quickstart.md) part A, plus the full backend suite offline.

### Tests for User Story 1 (write first, see them fail)

- [X] T033 [P] [US1] Write `backend/tests/contract/test_manifest_schema_compat.py`. The Pydantic models in `src/pricing_data/manifest.py` must parse every `examples` entry in the vendored `latest.schema.json` and `manifest.schema.json`, and the generated fixture's manifest. Documents valid under the schema with unknown optional fields (minor version) must parse with `extra="ignore"`.
- [X] T034 [P] [US1] Write `backend/tests/unit/test_manifest.py` for the pure validation `validate_manifest(manifest, provider, *, pointer=None) -> Manifest | RejectedManifest` (data-model §3). Use every file in `tests/fixtures/manifests/`:
  - `partial`, `failed` and `purged` are rejected with a reason
  - each bad path is rejected before any I/O, and a mock store confirms no `get` or `download` call
  - an unsupported major version or schema version is rejected
  - the pointer date mismatch and a revision below the pointer are rejected
  - the minor bump is accepted
- [X] T035 [P] [US1] Write `backend/tests/unit/test_snapshot_selection.py` for `select_snapshot(store, provider, pinned_date) -> Selection` using `make_pipeline_root`:
  - the newest is chosen from `latest.json`
  - the pin selects that date's manifest
  - a pin on a purged, partial or missing date gives `ActiveSnapshotConfigError` at startup
  - a missing `latest.json` (and an `AccessDenied` from the fake S3) gives "no snapshot available", not an error
  - a rejected manifest keeps the previous active snapshot and records `rejected`
  - an old-layout directory (table folders with `_SUCCESS` and no `aws/manifests`) gives the "unsupported layout, convert with upload-history" message
  - `previous_snapshot(store)` (used by T044) returns the newest `succeeded` manifest date before the active one, skips `partial`, `failed` and `purged` dates, and returns `None` when there is none
- [X] T036 [P] [US1] Write `backend/tests/unit/test_snapshot_cache.py` for `src/pricing_data/snapshot_cache.py` against the fake S3:
  - a fetch writes to `.tmp-*` and appears as `<date>-r<rev>` only after all files verify
  - a sha256 mismatch, a size mismatch or a 404 leaves no entry and reports the reason
  - a second `ensure_cached` of a verified entry makes no S3 calls
  - leftover `.tmp-*` directories are deleted by `startup_cleanup()`
  - a snapshot larger than `PRICING_CACHE_MAX_BYTES` is refused without download
  - a snapshot larger than the cache filesystem's free space (from an injected `disk_free` function) is refused without download, the current snapshot stays active, and the reason names the free space (spec edge case)
  - a fetch running longer than the grace period re-reads the manifest and restarts if the revision changed (use an injected clock)
- [X] T037 [P] [US1] Write `backend/tests/integration/test_pricing_from_manifest.py`:
  - `lookup_price`, catalog search and `list_available_regions` work against the new-layout fixture through `PRICING_DATA_URI=file://…`
  - a snapshot with **two** files per region (the second added through `extra_files` and listed in the manifest) counts rows from both
  - an unlisted extra file in the same folder is **not** read (no double counting, FR-004)
- [X] T097 [P] [US1] Write failing tests for snapshot revision traceability (FR-059, constitution I):
  - in `backend/tests/contract/test_calculate.py` and `backend/tests/contract/test_catalog.py`: the responses carry `snapshot_revision` (int) next to `snapshot_date`, matching the active snapshot's manifest
  - in `backend/tests/integration/test_pricing_from_manifest.py`: after switching from revision 1 to revision 2 of the **same date** (built with `make_pipeline_root`), a calculation reports `snapshot_revision: 2`
  - in `frontend/tests/unit/` for `PricingPanel.tsx`: the panel shows the revision next to the snapshot date
- [X] T038 [US1] Update the existing tests that set `aws_pricing_parquet_dir` or `AWS_PRICING_PARQUET_DIR` to use `PRICING_DATA_URI` pointing at the fixture root: `backend/tests/conftest.py`, `tests/unit/test_regions.py`, `tests/contract/test_request_logging.py`, `tests/contract/test_catalog.py`, `tests/integration/test_standard_architecture_pricing.py` and `tests/integration/test_standard_architecture_seed.py`. Rewrite `tests/unit/test_active_snapshot.py` to the new selection model (the `_SUCCESS`, waiting and marker cases are removed and replaced by T035).

### Implementation for User Story 1

- [X] T039 [US1] Implement `backend/src/pricing_data/manifest.py`:
  - strict Pydantic models `LatestPointer` and `Manifest` (nested `Regions`, `Run`, `Table`, `RegionFiles`, `DataFile`), with `extra="ignore"` and the required fields per the schema
  - `SUPPORTED_MANIFEST_MAJOR = 1` and `SUPPORTED_SCHEMA_VERSIONS = {t: {1} for t in TABLES}`
  - `validate_manifest(...)` and the path regex (data-model §3)

  Make T033 and T034 pass.
- [X] T040 [US1] Rewrite `backend/src/pricing_data/snapshot.py`:
  - keep `TABLES`
  - add the frozen dataclass `ActiveSnapshot(provider, snapshot_date, revision, manifest, base_dir, pinned)` with `files(table, region) -> list[str]` (absolute paths of the manifest's files under `base_dir`), `regions(table) -> set[str]` and `common_regions()`
- [X] T041 [US1] Implement `backend/src/pricing_data/snapshot_cache.py`: `ensure_cached(store, manifest, cache_dir, max_bytes, clock, disk_free=shutil.disk_usage) -> Path` (checks size limit and free space first, then verify-then-rename, writes `cache-entry.json`), `list_entries(cache_dir)` and `startup_cleanup(cache_dir)`. Make T036 pass. The clean-up policy is in T074.
- [X] T042 [US1] Rewrite `backend/src/pricing_data/active_snapshot.py`:
  - `select_snapshot(...)` (pure plus store reads) builds the `ActiveSnapshot`: a local source uses the root in place, and an S3 source goes through `ensure_cached`.
  - The new `MonitorState` (data-model §5) replaces `ActiveSnapshotState`, with no `waiting`, markers or `pinned_incomplete`.
  - `run_check(at_startup)` stays serialized with the lock.
  - `get_active_snapshot() -> ActiveSnapshot` replaces `get_active_snapshot_date()`, which is kept as a thin wrapper returning `.snapshot_date` for callers outside pricing data.
  - Startup still raises `ActiveSnapshotConfigError` for a bad pin.
  - Log transitions with the same event names as feature 017 where they still apply (`active pricing snapshot selected` and `changed`), plus `pricing snapshot rejected`.

  Make T035 pass.
- [X] T043 [US1] Change the query modules to take file lists from the active snapshot, with no path building:
  - In `backend/src/pricing_data/pricing.py` and `catalog.py`, replace `_price_fact_path`, `_product_dim_path` and `_service_dim_path` with `snapshot.files(table, region)`, and pass the list to `read_parquet(?)`. DuckDB accepts a list parameter.
  - Each public function takes the `ActiveSnapshot` once at its start (or as an optional argument), so one request never mixes snapshots.
  - If a region has no files for a table, raise the same error the old missing-path case produced.
- [X] T098 [US1] Add `snapshot_revision: int` to `CalculationResult` and `CatalogSearchResult` in `backend/src/models/schemas.py`, filled from the same `ActiveSnapshot` the request used (T043), in `backend/src/api/calculate.py` and `backend/src/api/catalog.py`. Regenerate `frontend/src/api/generated/schema.d.ts` (`npm run generate-api-types`), and show the revision in `frontend/src/components/workspace/PricingPanel.tsx` next to the snapshot date (for example `2026-10-05 r2`). Make T097 pass.
- [X] T044 [US1] Change `backend/src/pricing_data/regions.py` to `snapshot.common_regions()`, and `backend/src/pricing_data/icon_coverage.py` to read `service_dim` files from `snapshot.files("service_dim", r)` for all regions. `previous_present_date` becomes `previous_snapshot(store)`, the newest `succeeded` manifest date before the active one, from `list_manifest_dates`.
- [X] T045 [US1] In `backend/src/main.py`, apply `DUCKDB_MEMORY_LIMIT` and `DUCKDB_THREADS` to every DuckDB connection the pricing modules create. Add a small `pricing_data/duckdb_conn.py` factory used by `pricing.py`, `catalog.py` and `icon_coverage.py`. Call `snapshot_cache.startup_cleanup` in the lifespan before the first `run_check`.
- [X] T046 [US1] Make the old-layout and old-setting failures user-facing. When `select_snapshot` sees an old-layout directory at startup, raise `ActiveSnapshotConfigError` with the conversion instructions (quickstart A1). Confirm the `AWS_PRICING_PARQUET_DIR` guard from T009 triggers when the server starts through `bin/start_back.sh`.
- [X] T047 [US1] Run the whole backend suite (`uv run pytest`) and `uv run ruff check src/`. Fix every failure caused by the new model. No test may need network access.
- [X] T048 [P] [US1] Update `backend/.env.example` (remove `AWS_PRICING_PARQUET_DIR`, add `PRICING_DATA_URI=file:///path/to/DATA/pipeline` and the cache and DuckDB settings, commented), `backend/README.md`, and the settings table in `docs/configuration.md` per [contracts/configuration.md](./contracts/configuration.md). Update `backend/scripts/generate_aws_service_icon_map.py` and `backend/scripts/resolve_standard_architectures.py` to take `--data-uri` and read through the manifest (`select_snapshot` plus `files()`) instead of the old directory.
- [X] T049 [US1] Update `.github/workflows/ci.yml`: replace `AWS_PRICING_PARQUET_DIR` with `PRICING_DATA_URI: file://${{ github.workspace }}/backend/tests/fixtures/pricing_parquet`.

**Checkpoint**: US1 works on its own. The laptop runs against a local root offline, and an `s3://` source works through the cache (proven with the fake S3 in tests, and against real S3 in US2).

---

## Phase 4: User Story 2 - Bring the whole app up in the cloud with one action (Priority: P1)

**Goal**: `deploy/app up` and the `app` workflow create the instance, start the stack, restore the database, serve HTTPS on the IP and report the address, with health confirmed through SSM.

**Independent test**: [quickstart.md](./quickstart.md) parts D and E steps 2–8. A backup can be seeded with `ops backup` (Phase 2) or come from a previous `down` (US3).

### Tests for User Story 2

- [ ] T050 [P] [US2] Write `infra/instance/tests/instance.tftest.hcl` (mocked provider, plan) asserting contracts/infrastructure.md tests 1–3:
  - no bucket, parameter, log group, SNS or IAM resources
  - ingress is exactly 443 from each allowlist entry, with no 22, no 80 and no `0.0.0.0/0`
  - `http_tokens = "required"`, an encrypted root volume with `delete_on_termination`, a public IP and no EIP
  - `user_data_replace_on_change = true`
  - the user-data contains both image digests and no secret values
- [ ] T051 [P] [US2] Write `backend/tests/unit/test_ops_health.py` for `src/ops/health.py` with stubbed HTTP, a stubbed database check and a stubbed `db-init.json`:
  - `healthy: true` with `pricing: ok`
  - `healthy: true` with `pricing: unavailable` and a reason (Story 2 AS4)
  - `healthy: true` when the Admin password differs from the SSM owner password (the check never reads that parameter, FR-028)
  - `healthy: false` when the Admin row is missing or inactive, or when the login endpoint answers anything but `401` for a random non-existent username
  - `healthy: false` when `db-init.json` reports failure, with the log tail included
  - `--wait` times out with `healthy: false`

  Also write `backend/tests/contract/test_health.py`: `GET /health` needs no auth and returns `{"status": "ok", "pricing": "ok"|"unavailable", "pricing_reason": str|null}`; with no active snapshot, `pricing` is `unavailable` and the reason is a fixed phrase with no path or exception text ([contracts/admin-api.md](./contracts/admin-api.md)).
- [ ] T052 [P] [US2] Extend `deploy/tests/app_test.sh` for `up`:
  - **Release resolution**: picks the highest semver tag present in **both** repositories from stubbed `ecr describe-images` output; a named missing release gives exit 3 "not in this environment's registry" before any `tofu` call.
  - **TLS root**: a missing root with no backups creates it; a missing root with existing backups gives exit 3 unless `--new-root`; a root that expires within 180 days prints a warning naming the expiry date, puts it in the notice, and does not fail or replace the root.
  - **Plan leaves the instance alone while up** (stubbed `tofu show -json` with no `aws_instance` change): no backup step, and the saved plan is applied.
  - **Plan replaces the instance while up**, for each cause (different release, different `ami_id`, different `db_init_args`): a `redeploy` backup through SSM runs before `tofu apply`, and a failed or unverified backup aborts with exit 4 and no apply.
  - **Apply uses the saved plan**: `tofu apply` is called with the plan file, never with `-auto-approve` and fresh variables.
  - **Health**: an unhealthy result gives exit 5.

### Implementation for User Story 2

- [ ] T053 [US2] Create the cloud-init template `deploy/host/cloud-init.yaml.tftpl`:
  - **Packages**: `docker.io`, `docker-compose-v2`, `amazon-ecr-credential-helper` (from the Ubuntu archive, confirmed by T054).
  - **Swap**: a 2 GiB swap file.
  - **Docker**: `/root/.docker/config.json` with `credHelpers` for `<account>.dkr.ecr.<region>.amazonaws.com` set to `ecr-login`.
  - **Files**: `/opt/app/compose.yaml` (the T024 file, embedded by templatefile) and `/opt/app/.env`, holding:
    - `BACKEND_IMAGE` and `WEB_IMAGE` by digest
    - `APP_RELEASE` and `APP_ENVIRONMENT`
    - `PRICING_DATA_URI=s3://<data bucket>`
    - `BACKUP_URI`, `ALERT_TOPIC_ARN`, `OWNER_PASSWORD_PARAMETER`, `LOG_GROUP`, `AWS_REGION`
    - `DB_INIT_ARGS` (for `--backup`)
  - **Boot script**:
    1. Read `PUBLIC_ADDRESS` from IMDSv2 and append it to `.env`.
    2. Generate a random Postgres password into `/opt/app/secrets/db_password` (mode 0400).
    3. Run `docker compose up -d`.
  - **Timers**: the systemd units from T066 and T085. Install now as no-op stubs if those stories aren't done.
- [ ] T054 [US2] Verify the host package plan before relying on it: confirm `amazon-ecr-credential-helper`, `docker.io` and `docker-compose-v2` exist for Ubuntu 24.04 `arm64` (packages.ubuntu.com, noble, universe), and that Canonical's public SSM parameter `/aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id` resolves in `us-east-1`. Record the findings in research.md R4. If the helper is missing, switch to fetching an ECR token from the backend image (`python -m src.ops ecr-login`) and note it there.
- [ ] T055 [US2] Create `infra/instance/` (`versions.tf`, `providers.tf`, `variables.tf`, `network.tf`, `instance.tf`, `outputs.tf`):
  - **Inputs**: environment, region, `ami_id`, `instance_type`, `root_volume_gib`, `release`, `backend_digest`, `web_digest`, `db_init_args`.
  - **Base stack values**, read through `terraform_remote_state` on `app/<env>/base.tfstate`.
  - **Allowlist**: `data "aws_ssm_parameter"`. The placeholder `none` means no ingress rule.
  - **Network**: VPC `10.40.0.0/24`, one public subnet, an IGW and a route table.
  - **Security group**: one `aws_vpc_security_group_ingress_rule` per address on 443, and egress all.
  - **Instance**: `aws_instance` with the base instance profile, `metadata_options { http_tokens = "required" }`, an encrypted gp3 root, `associate_public_ip_address = true`, `user_data_base64 = base64gzip(templatefile(...))` and `user_data_replace_on_change = true`.
  - **Outputs**: `instance_id`, `public_ip` (marked `sensitive`), `release`, plus the inputs that change user-data (`ami_id`, `backend_digest`, `web_digest`, `db_init_args`), so that `allow` can re-apply with the running instance's own values (T081).

  Make T050 pass.
- [ ] T099 [US2] Generate the provider lock file for `infra/instance` with `tofu providers lock -platform=linux_arm64 -platform=linux_amd64 -platform=darwin_arm64` and commit `infra/instance/.terraform.lock.hcl` (the second half of T030).
- [ ] T056 [US2] Change `GET /health` in `backend/src/main.py` to return a `HealthOut` model (in `backend/src/models/schemas.py`) with the pricing state from the snapshot monitor, and regenerate the frontend types. Implement `backend/src/ops/health.py` (`health --wait`): poll `db-init.json` and `http://backend:8000/health`, check that the default Admin row exists and is active (direct database query through the ORM), check that `POST /api/v1/auth/login` returns `401` for a random non-existent username, and take the pricing state from `/health`. It never reads the owner password parameter (FR-028). Wire it in `__main__.py`. Make T051 pass.
- [ ] T057 [US2] Implement `deploy/app up` per research R11 and [contracts/app-cli.md](./contracts/app-cli.md):
  1. Preflight: `sts get-caller-identity`, base outputs, the allowlist parameter is readable, the AMI exists, and the release is in both repositories (`ecr describe-images`).
  2. Take the lock.
  3. Resolve the digests.
  4. Ensure the TLS root (T058).
  5. `tofu plan -out=<tmp>/instance.plan` on `infra/instance` with the vars, then `tofu show -json` on it. If a running `aws_instance` would be replaced or destroyed (its `change.actions` contains `delete`), run `ssm_run … "cd /opt/app && docker compose stop web backend && docker compose run --rm ops backup --kind redeploy"` and require `verified: true`. If the backup fails or isn't verified, exit 4 without applying (FR-029).
  6. `tofu apply <tmp>/instance.plan` (the saved plan, so what was checked is what is applied).
  7. Wait for the SSM agent to come online (`describe-instance-information`, 5 min timeout).
  8. `ssm_run … "docker compose -f /opt/app/compose.yaml run --rm ops health --wait 600"`.
  9. Print the result (masked address in GitHub), and send the address notice through `ssm_run … ops notify`.
  10. Release the lock.

  Exit 0 with the pricing warning when `pricing: unavailable`. Make T052 pass.
- [ ] T058 [US2] Implement TLS root creation inside `deploy/app` (function `ensure_tls_root`):
  - If `/cloud-pricing-app/$ENV/tls/root-cert` is missing and the backup bucket has no `<env>/db/*.json`, generate an EC P-256 key and a 5-year self-signed CA cert (`CN=cloud-pricing-app $ENV root`, `basicConstraints=critical,CA:TRUE`, `keyUsage=critical,keyCertSign,cRLSign`) with `openssl` in a `mktemp -d` directory that is removed on exit.
  - Store the key as a SecureString and the cert as a String. Print "NEW ROOT CREATED – install it on your devices (deploy/app cert)".
  - If it is missing and backups exist, exit 3 unless `--new-root`.
  - If it exists and expires within 180 days (`openssl x509 -checkend`), print a warning with the expiry date and include it in the "up" notice. Don't fail and don't replace it. Replacing it stays a deliberate `--new-root` action (spec edge case, research R6).
  - Never print the key.
- [ ] T059 [US2] Create `.github/workflows/release.yml` per contracts/app-cli.md:
  - **Triggers**: `push` with tags `v*`, and `workflow_dispatch` with a `tag` input.
  - **Job**: `runs-on: ubuntu-24.04-arm`, a matrix from `fromJSON(vars.RELEASE_ENVIRONMENTS || '["prod"]')`, where the variable holds a JSON list, and `permissions: id-token: write, contents: read`.
  - **Steps**: checkout at the tag; configure AWS credentials with `secrets[format('AWS_ROLE_RELEASE_{0}', upper(matrix.env))]` and `mask-aws-account-id: true`; ECR login; for backend and web, `aws ecr describe-images` (skip if the tag exists) and otherwise `docker buildx build --platform linux/arm64 --push` with `GIT_SHA` and `RELEASE` build args; write the digests to `$GITHUB_STEP_SUMMARY`.
- [ ] T060 [US2] Create `.github/workflows/app.yml` per contracts/app-cli.md:
  - **Trigger**: `workflow_dispatch` with inputs `action` (choice), `environment` (choice `prod`), `release`, `backup`, `address` and `force_without_backup`.
  - **Job**: `environment: ${{ inputs.environment }}`, `concurrency: { group: app-${{ inputs.environment }}, cancel-in-progress: false }`, `permissions: id-token: write, contents: read`.
  - **Steps**: first, mask `inputs.address` and `inputs.release`; checkout; set up OpenTofu `1.10.6` with `tofu_wrapper: false`; configure AWS credentials with `secrets[format('AWS_ROLE_DEPLOY_{0}', upper(inputs.environment))]` and `mask-aws-account-id: true`; then run `deploy/app ${action} --env ${environment} …` with `AWS_REGION: ${{ vars.AWS_REGION }}`.
- [ ] T061 [P] [US2] Create `.github/workflows/oidc-subject.yml` (manual; prints `sub`, `ref`, `environment` and `event_name` from `core.getIDToken('sts.amazonaws.com')`, never the token), mirroring the pipeline repo's version (FR-051).
- [ ] T062 [US2] Create `compose.local.yaml`, the override for the local packaged stack (also used to smoke-test US2 images before AWS):
  - builds `backend` and `web` from the local Dockerfiles
  - `logging: driver: json-file`
  - `PRICING_DATA_URI=file:///data` with a read-only bind mount of `${LOCAL_DATA_ROOT}`
  - `BACKUP_URI=file:///backups` bound to `./.local-backups`
  - `TLS_ROOT_DIR=/local-tls` bound to `./.local-tls`
  - `HTTPS_PORT=8443`, `PUBLIC_ADDRESS=localhost`
  - no `ALERT_TOPIC_ARN`
  - the owner password from `.env.local`
- [ ] T063 [US2] Smoke-test the images locally: `docker compose -f compose.yaml -f compose.local.yaml up --build`, then `docker compose run --rm ops health --wait 120` returns `healthy: true` and `db: fresh`. Fix the Dockerfile and Compose issues found. This needs Docker on the laptop (quickstart prerequisites).

**Checkpoint**: from an environment with the base stack and one release, `up` gives a working app, by tests plus quickstart D (run in Phase 11 together with US3 and US4).

---

## Phase 5: User Story 3 - Tear down safely, with no data loss (Priority: P1)

**Goal**: `down` takes and verifies a final backup, then destroys only the instance stack. If the backup fails, nothing is destroyed.

**Independent test**: [quickstart.md](./quickstart.md) parts E and F.

### Tests for User Story 3

- [ ] T064 [P] [US3] Extend `deploy/tests/app_test.sh` for `down`:
  - with no instance in state: exit 0, with no SSM or destroy call
  - a backup with `verified: false`, or an SSM failure: exit 4 and **no** `tofu destroy` call
  - `--force-without-backup`: destroy is called and a warning is printed
  - success: the call order is lock → SSM stop and backup → destroy → `describe-instances` confirms none with the tags → unlock

### Implementation for User Story 3

- [ ] T065 [US3] Implement `deploy/app down` and `deploy/app backup-now` per research R11:
  - **`down`**: read the instance id from the instance-stack outputs, or by tags if the outputs are missing; `ssm_run … "docker compose stop web backend && docker compose run --rm ops backup --kind teardown"`; parse the JSON and require `verified: true`; then `tofu destroy -auto-approve`, and confirm no tagged instance remains.
  - **`backup-now`**: SSM `ops backup --kind manual`.

  Make T064 pass.
- [ ] T066 [US3] Create the scheduled backup units `deploy/host/app-backup.service` and `deploy/host/app-backup.timer` (`OnBootSec=1h`, `OnUnitActiveSec=6h`, `Persistent=true`; the service runs `docker compose -f /opt/app/compose.yaml run --rm ops backup --kind scheduled`). Install and enable them in `deploy/host/cloud-init.yaml.tftpl`. The backup command already alerts on failure (T016).

**Checkpoint**: US2 and US3 together give the full on-demand cycle.

---

## Phase 6: User Story 4 - First-ever deployment into an empty environment (Priority: P2)

**Goal**: the documented one-time setup, then a single `up` works from nothing.

**Independent test**: [quickstart.md](./quickstart.md) parts C and D.

- [ ] T067 [US4] Write `docs/deployment.md`, the runbook (FR-046, FR-054), with two separate parts:
  - **One-time setup per account and environment**: the quickstart C steps in order, each with its check command. Before applying the base stack, one check command per account-wide item (OIDC provider, state bucket, data bucket, data read policy) prints which item is missing and that it comes from cloud-pricing-data-retrieval (FR-056). The steps include:
    - the OIDC subject template (`["repo","context","ref"]`, using a temporary token deleted afterwards)
    - the GitHub environment
    - the secrets `AWS_ROLE_PLAN_<ENV>`, `AWS_ROLE_DEPLOY_<ENV>` and `AWS_ROLE_RELEASE_<ENV>`
    - the variables `AWS_REGION`, `RELEASE_ENVIRONMENTS` (JSON list, e.g. `["prod"]`) and `AWS_PLAN_ENABLED`
    - the `v*` tag ruleset and the `main` ruleset
    - the AMI ID
    - applying the base stack
    - confirming the SNS subscription
    - `aws ssm put-parameter` for `owner-password`
    - the first `allow add`
    - the `oidc-subject` check
    - the first release tag
  - **Routine operation**: up, down, status, allow, backup-now, choosing a release or backup, rollback, the lock, reading logs (CloudWatch group), Session Manager shell, updating the AMI (`ami-latest`), adding an environment (add it to `RELEASE_ENVIRONMENTS` **before** tagging), and installing the root on macOS, iOS and Android.
  - **Answered questions**: a section for findings checked and dismissed, with evidence (FR-055). Start it with research R13's result (T091).
- [ ] T068 [US4] Add the first-deploy guards to `deploy/app up` preflight, each failing with exit 3 and the runbook step to do:
  - the owner-password parameter is missing
  - the allowlist is the placeholder `none` (warn only: "nobody can reach the app")
  - the base stack outputs are missing
  - the AMI placeholder is still in tfvars
  - extend `deploy/tests/app_test.sh` to cover these guards
- [ ] T069 [US4] Confirm that environments are isolated (FR-034) with a `tofu test` run in `infra/base/tests/base.tftest.hcl` using `environment = "qa"`: every name, the state key prefix, the parameter paths and the trust subjects contain `qa` and never `prod`. Do the same for `infra/instance/tests/instance.tftest.hcl`.

**Checkpoint**: a new environment can be set up from the runbook alone.

---

## Phase 7: User Story 5 - New pricing data is picked up while the app is running (Priority: P2)

**Goal**: background and manual checks switch to new snapshots or revisions safely, clean the cache, and show everything in the Admin tab.

**Independent test**: [quickstart.md](./quickstart.md) part H, and locally by publishing a second snapshot into the local root while the app runs.

### Tests for User Story 5

- [X] T070 [P] [US5] Write `backend/tests/unit/test_snapshot_monitor.py` with `make_pipeline_root` and an injected clock:
  - a newer `succeeded` date switches, and `previous_date` is recorded
  - a newer revision of the same date switches
  - a `partial` newest run does not switch, and `latest_run` shows it with failed regions
  - an unreachable source (the fake store raises) keeps the active snapshot and sets `last_check_error`
  - a checksum failure keeps the active snapshot, records `rejected`, and is retried at the next check
  - `missing_regions` is computed from `regions.failed`
  - the icon analysis runs on a switch only
- [ ] T071 [P] [US5] Write `backend/tests/unit/test_cache_cleanup.py` for `plan_cleanup(entries, active, keep, max_bytes, superseded_this_check) -> list[Path]`:
  - the active entry is never deleted
  - a superseded entry is never deleted by the check that superseded it; at the next check it is deleted if it is excess, and kept if it is within `keep`, within the size limit and not purged (FR-011)
  - entries beyond `keep` are deleted oldest first
  - the size limit is enforced
  - entries whose manifest is now `purged` are deleted
- [ ] T072 [P] [US5] Update `backend/tests/contract/test_admin_system_info.py` to the new response shape in [contracts/admin-api.md](./contracts/admin-api.md): `source` never contains credentials, the cache section is `null` for a local source, and there is no `waiting_snapshots`. Add `backend/tests/contract/test_admin_snapshot_check.py`: the endpoint is admin-only (403 otherwise), returns 202 `{"started": true}`, and returns 409 while a check runs (hold the monitor lock in the test).
- [ ] T073 [P] [US5] Write a no-failed-requests test in `backend/tests/integration/test_snapshot_switch_concurrency.py`. A thread loops `lookup_price` on a fixture SKU while the main thread switches between two snapshots 20 times; every call returns a price from one consistent snapshot, with no exception (SC-007).

### Implementation for User Story 5

- [ ] T074 [US5] Implement `plan_cleanup` and `apply_cleanup` in `backend/src/pricing_data/snapshot_cache.py`, call them at the end of each `run_check`, passing the entry that this check superseded (if any) so it is spared until the next check. No per-entry timestamps are needed. Make T071 pass.
- [ ] T075 [US5] Complete the monitor in `backend/src/pricing_data/active_snapshot.py`:
  - revision changes and `latest_run` (newest dated manifest, any status, through `list_manifest_dates`)
  - `rejected`, `missing_regions` from the manifest
  - the icon analysis on a switch
  - the grace re-read for long fetches

  Make T070 and T073 pass.
- [ ] T076 [US5] Update `backend/src/models/schemas.py` (new `SystemInfoOut`, `ActiveSnapshotOut`, `LatestRunOut`, `CacheOut`, `CacheEntryOut`, `DeploymentOut`, `SourceOut`; `IssueOut.kind` becomes `missing_icon | missing_regions`; `WaitingSnapshotOut` is removed) and `backend/src/api/admin_system.py` (the new `system-info`, plus `POST /admin/pricing-snapshot/check`, which runs `run_check` in a thread and returns 202 or 409). Make T072 pass.
- [ ] T077 [US5] Regenerate the frontend types: start the backend, run `npm run generate-api-types` in `frontend/`, and commit `frontend/src/api/generated/schema.d.ts`.
- [ ] T078 [US5] Update `frontend/src/components/admin/SystemInformationSection.tsx` to show:
  - deployment (environment, release)
  - source (kind, location)
  - the active snapshot (date, revision, run id, pipeline version, created at, pinned badge, regions, failed regions)
  - the latest pipeline run (status badge, failed regions with reasons)
  - the last rejected manifest
  - the cache (entries with state and size, total of limit, as a percentage)
  - last check and error, and issues
  - a **Check now** button that calls the new endpoint, disables itself while a check runs, and re-fetches `system-info` until `last_check_at` changes (poll every 2 s, up to 60 s)

  Remove the waiting-snapshots table. Follow the existing shadcn/ui components and styles in that file.
- [ ] T079 [US5] Update `frontend/tests/unit/SystemInformationSection.test.tsx` for the new shape: a local source hides the cache; a partial latest run shows its failed regions; Check now calls the endpoint, then refreshes, and shows the 409 message. Run `npm run lint`, `npm run build` and `npm test` in `frontend/`.

**Checkpoint**: snapshot updates are visible and safe, and the Admin tab reflects every state in data-model §5.

---

## Phase 8: User Story 6 - Private access only (Priority: P2)

**Goal**: an allowlist managed with one action, HTTPS only through the per-environment root, no other inbound access, and a keyless shell.

**Independent test**: [quickstart.md](./quickstart.md) part G.

- [ ] T080 [P] [US6] Extend `deploy/tests/app_test.sh` for `allow`:
  - `add` accepts IPv4 (stored as `/32`) and IPv6 (stored as `/128`), and rejects ranges, hostnames and empty input with exit 2
  - duplicate add is a no-op
  - remove of a missing entry is a no-op with a message
  - the list is printed after each change
  - over 50 entries gives exit 2
  - with the instance up, `tofu plan` on `infra/instance` runs with the values from the instance-stack outputs (`release`, `ami_id`, `backend_digest`, `web_digest`, `db_init_args`), not from tfvars or defaults, and the saved plan is applied; with it down, no `tofu` call
  - if that plan would replace or destroy the instance (stubbed `tofu show -json`), exit 3 with "run up instead", the plan is not applied, and the parameter is written back to its previous value (`put-parameter` called with the old list), so nothing changes (FR-029)
  - the lock is taken for add and remove
- [ ] T081 [US6] Implement `deploy/app allow add|remove|list` (`ssm get-parameter` and `put-parameter --overwrite` on the StringList; replace the placeholder `none` on the first add; restore `none` when the last entry is removed; when the instance is up, plan with the running instance's values from the instance-stack outputs and apply the saved plan only if it leaves the `aws_instance` untouched, otherwise restore the previous parameter value and exit 3; share the plan-inspection helper with T057) and `deploy/app cert [--out]` (prints the root cert from SSM). Also implement `deploy/app cert local --create`, which generates the laptop root into `./.local-tls/` for `compose.local.yaml`, using the same openssl recipe as T058. Make T080 pass.
- [ ] T082 [US6] Implement `deploy/app ami-latest` (prints the Canonical parameter value for `AWS_REGION`, the arm64 gp3 Ubuntu 24.04 path from T054). Add the related lines to `docs/deployment.md`.
- [ ] T083 [US6] Add the device-trust instructions to `docs/deployment.md`:
  - **macOS**: Keychain Access → import → Always Trust.
  - **iOS**: AirDrop or email the `.crt`, install the profile, then Settings → General → About → Certificate Trust Settings → enable.
  - **Android**: Settings → Security → Encryption & credentials → Install a certificate → CA certificate.
  - A note that the root never changes unless `--new-root` is used.

**Checkpoint**: only allowlisted devices that trust the root can use the app.

---

## Phase 9: User Story 7 - Protection against a forgotten instance and cost overruns (Priority: P3)

**Goal**: alert by email when the app has been up longer than the threshold, and repeat at an interval. No automatic teardown.

**Independent test**: [quickstart.md](./quickstart.md) part I step 3.

- [ ] T084 [P] [US7] Write `backend/tests/unit/test_uptime_alert.py` for `src/ops/uptime.py` with injected uptime, now and state file:
  - below the threshold: no alert
  - first crossing: an alert, and the state file is written
  - within the repeat interval: no alert
  - after the interval: another alert
  - a notify failure is logged and doesn't raise
- [ ] T085 [US7] Implement `backend/src/ops/uptime.py` (`uptime-alert` reads `/proc/uptime` from the host through a read-only bind mount `/host/proc/uptime:ro` declared on the `ops` service in `compose.yaml`, keeps state in `/var/lib/app/last-uptime-alert`, and calls `alerts.notify`), and wire it in `__main__.py`. Create `deploy/host/app-uptime.service` and `app-uptime.timer` (`OnUnitActiveSec=30min`) and enable them in the cloud-init template. Make T084 pass.

**Checkpoint**: a forgotten instance is reported within 30 minutes of the threshold.

---

## Phase 10: User Story 8 - Run the production-like stack on a laptop (Priority: P3)

**Goal**: the same Compose stack runs locally with local data and backups, and the non-packaged workflow stays unchanged.

**Independent test**: [quickstart.md](./quickstart.md) part B.

- [ ] T086 [US8] Add `.env.local.example` at the repository root (`LOCAL_DATA_ROOT`, the owner password for the local `db-init`, `APP_ENVIRONMENT=local`) and the Story 8 section of `docs/deployment.md`: `cert local --create`, `docker compose -f compose.yaml -f compose.local.yaml up --build`, backup, wipe and restore (quickstart B steps 3–4), and seeding the cloud from local data (quickstart B5, with `BACKUP_URI=s3://…` and the owner's AWS profile).
- [ ] T087 [US8] Run quickstart B end to end on the laptop (fresh, then backup, `down -v`, restore) and quickstart A step 3 with `bin/start_back.sh` and `bin/start_front.sh` (non-packaged, unchanged scripts). Record the results in the PR description.

**Checkpoint**: all stories are done.

---

## Phase 11: Polish, CI and real-account acceptance

**Purpose**: the pipeline lessons applied (FR-045 to FR-055), CI gates, and the measurements required before acceptance.

- [ ] T088 Update `.github/workflows/ci.yml` (FR-052, FR-053):
  - pin every action to a full SHA, and use `runs-on: ubuntu-24.04`
  - backend job: install `postgresql-client-18` (PGDG) so `test_backup_roundtrip.py` and `test_db_init_restore.py` run in CI
  - new `infra` job: `tofu fmt -check -recursive infra/`, then `tofu init -backend=false` plus `validate` plus `test` for `infra/base` and `infra/instance`
  - new `deploy` job: `shellcheck deploy/app deploy/tests/app_test.sh`, then `bash deploy/tests/app_test.sh`
  - new `images` job (on `ubuntu-24.04-arm`): `docker buildx build --platform linux/arm64` for `backend/Dockerfile` and `frontend/Dockerfile.web`, with no push
  - new `plan` job: only on `pull_request` when `vars.AWS_PLAN_ENABLED == 'true'`; assumes `AWS_ROLE_PLAN_PROD` with account-ID masking; runs `tofu plan` for `infra/instance` with the newest release digests or placeholder values, and posts the summary as a PR comment, like the pipeline repo
- [ ] T089 [P] Check that no secrets or identifiers leak (FR-041, FR-050, SC-013): add `backend/tests/contract/test_no_secret_logging.py` (ops `db-init`, `backup` and `fetch-tls` never log the owner password, TLS key or database password; reuse the pattern in `test_log_secrets.py`), and a CI step that greps the repository for 12-digit AWS account IDs outside `infra/envs/*.example` and fails on a match.
- [ ] T090 [P] Record the pinned versions and how to upgrade them in `docs/deployment.md` (FR-053): base image digests, the Action SHAs, OpenTofu, provider lock platforms, the PGDG key fingerprint, the AMI (`ami-latest`), and the `uv` image digest.
- [ ] T091 Verify research R13: start a throwaway `workflow_dispatch` run of `app.yml` with `action=allow-list` and a dummy `address`. While logged out (a private browser window) and through the unauthenticated REST API (`GET /repos/grp3d/cloud-pricing-app/actions/runs/<id>`), check whether the input value is visible. Record the answer and evidence in `docs/deployment.md` under "Answered questions" (FR-055), and adjust the runbook advice if it is visible.
- [ ] T092 Real-account acceptance, following quickstart C → I in order on `prod`, recording every result and timing in `specs/018-app-cloud-deployment/acceptance.md`:
  - first `up` (fresh database, new root)
  - 10 down/up cycles (SC-002)
  - a redeploy with a new tag
  - the replacement guard, the password-independent health check, the `status` address email and the revision label (E steps 5–8)
  - the backup-failure test (F)
  - the access tests (G)
  - a new pipeline snapshot (H)
  - the release, pricing-unavailable and uptime checks (I)

  Any permission error found here is fixed in `infra/base` **together with a new assertion** in `base.tftest.hcl` (FR-045). It is never fixed by hand in the console.
- [ ] T093 Measure memory on the `t4g.small` (research R3): during T092, run the standard-architecture pricing scenario through the UI and record peak RSS per container (`docker stats --no-stream` in a loop through Session Manager) in `acceptance.md`. If it is over 1.7 GiB total or there is swapping during requests, stop and raise it with the owner as a spec change. Don't silently resize.
- [ ] T094 Measure bring-up times (SC-001): a fresh `up` and a restore `up`, from workflow start to the health result, recorded in `acceptance.md`. If either is over 10 minutes, find the slow step (image pull, `apt install`, or restore) and fix it before acceptance.
- [ ] T095 [P] Final docs pass (FR-054): `docs/configuration.md`, `docs/deployment.md`, `backend/README.md` and the root `README.md` (a short "Deploying" section pointing to the runbook) describe the system exactly as built. Remove every mention of `_SUCCESS`, `AWS_PRICING_PARQUET_DIR` and the old fixture layout (`grep -rn` must find none outside `specs/0[01][0-7]-*`).
- [ ] T096 Remove dead code left by the rewrite: `make_snapshot_tree` in `backend/tests/helpers/parquet_tree.py` if it is unused, `_marker_mtimes`, `_scan`, `_waiting_reason` and the `pinned_incomplete` handling. Run `uv run ruff check src/` and the full test suites one last time.

---

## Dependencies and execution order

### Phase dependencies

- **Setup (Phase 1)**: none. T004 → T005 (the fixture comes from the script). T006 and T007 are independent.
- **Foundational (Phase 2)**: depends on Phase 1. Inside it:
  - T008 → T009
  - T010 → T011
  - T012, T013 → T014
  - T015 → T016
  - T017 → T018 (needs T014)
  - T019 can run in parallel; T020 after T016 and T018
  - T021–T023 in parallel; T024 after T021–T023; T025 after T020
  - T026 → T027 → T028; T029 in parallel; T030 after T027 (T099, the `infra/instance` lock file, follows T055 in US2)
  - T031 → T032
- **US1 (Phase 3)**: needs T009 and T011. Independent of all other stories. **MVP.** T097 → T098, which also needs T043.
- **US2 (Phase 4)**: needs Phase 2 and US1 (the cloud app must read S3 data). T054 before T053 and T055. T099 after T055.
- **US3 (Phase 5)**: needs Phase 2 (backup) and US2's `deploy/app up`, which produces the instance it tears down.
- **US4 (Phase 6)**: needs US2 and US3, since it documents and guards them.
- **US5 (Phase 7)**: needs US1 only. It can run in parallel with US2–US4.
- **US6 (Phase 8)**: needs US2 (instance stack and `up`). T081's `cert local` part is also needed by US8.
- **US7 (Phase 9)**: needs Phase 2 (alerts) and US2 (the cloud-init template).
- **US8 (Phase 10)**: needs T062 and T063 (from US2) and T081 (`cert local`).
- **Polish (Phase 11)**: T088–T091 any time after their inputs exist. T092–T094 need every story done and a release tagged.

### Story completion order

```text
Setup → Foundational → US1 (MVP) ─┬─► US2 → US3 → US4 ─┬─► US6 ─► US8 ─► Polish/acceptance
                                  │                     └─► US7 ──────────┘
                                  └─► US5 (parallel with US2–US4) ────────┘
```

### Within each story

Tests are written first and must fail (constitution V). Then models and pure functions, then I/O wrappers, then endpoints, scripts and UI. Commit at each checkpoint.

## Parallel opportunities

- **Phase 1**: T002, T003, T006 and T007 together.
- **Phase 2**: T010/T012/T013/T019 test files together; T021/T022/T023 (Dockerfiles, Caddyfile); T028 and T029.
- **US1**: T033–T037 and T097 (all test files) together, then T039/T040/T041 (separate modules).
- **US2**: T050, T051, T052 and T061 together.
- **US5**: T070–T073 together. US5 as a whole can run alongside US2–US4.
- **Polish**: T089, T090 and T095.

### Parallel example: User Story 1

```text
Task: "T033 [P] [US1] contract test: Pydantic models vs vendored schemas in backend/tests/contract/test_manifest_schema_compat.py"
Task: "T034 [P] [US1] manifest validation tests in backend/tests/unit/test_manifest.py"
Task: "T035 [P] [US1] snapshot selection tests in backend/tests/unit/test_snapshot_selection.py"
Task: "T036 [P] [US1] cache verify-then-rename tests in backend/tests/unit/test_snapshot_cache.py"
Task: "T037 [P] [US1] pricing-from-manifest integration tests in backend/tests/integration/test_pricing_from_manifest.py"
```

## Implementation strategy

### MVP first (User Story 1)

1. Phase 1 and the Phase 2 items US1 needs (T008–T011). The rest of Phase 2 can follow.
2. Phase 3 (US1). **Stop and validate** with quickstart A. The laptop now runs on the pipeline's current output. That is useful even before any cloud work, because the old layout is no longer produced.

### Incremental delivery

1. US1, merged. Local development is unblocked.
2. Finish Phase 2. Then US2 + US3 + US4, merged together, because "up" without a safe "down" isn't usable (the first real cloud cycle happens in T092).
3. US5 (parallel track), merged.
4. US6, US7 and US8, merged.
5. Phase 11 acceptance on `prod`.

### Complexity guard (FR-058)

Any task that finds it needs a new setting, stored item, scheduled job, permission or managed resource **not** listed in plan.md's configuration inventory must stop and add it there, with the requirement that needs it, before continuing. The owner reviews such additions.
