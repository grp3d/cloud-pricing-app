# Implementation Plan: On-Demand Cloud Deployment with Manifest-Driven Pricing Data

**Branch**: `018-app-cloud-deployment` | **Date**: 2026-10-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/018-app-cloud-deployment/spec.md`

## Summary

This feature has two parts that ship together.

**Pricing data from manifests.** The backend stops scanning `snapshot_date=` folders for `_SUCCESS` markers. It reads the pipeline's `latest.json` and manifests from one setting, `PRICING_DATA_URI`, which accepts a local directory or `s3://`. Every file a query reads comes from the manifest. S3 snapshots are copied once into a verified local cache and swapped in atomically.

**On-demand cloud deployment.** One script (`deploy/app`) and one workflow (`app.yml`) bring a single `t4g.small` Ubuntu instance up and down. Release images are built for each `v*` tag and stored in ECR, the same registry as the pipeline. Their repositories are in the long-lived base stack. The instance runs the app under Docker Compose: Caddy with a per-environment root CA for HTTPS on the IP, the backend, and Postgres. Each bring-up restores Postgres from the newest verified backup in S3, and each teardown first takes and verifies one. Long-lived resources are in a base stack applied once by the owner. The instance stack is the only thing "up" and "down" touch.

The design follows the lessons from the pipeline's deployment review: nothing long-lived in the disposable stack, real outcomes checked, explicit inputs, tests for the infrastructure, pinned tools, and a complete permission set. Per FR-058, it keeps the number of moving parts small and lists every one ([Configuration inventory](#configuration-inventory-fr-058)).

## Technical Context

**Language/Version**: Python 3.12 (backend and ops CLI), TypeScript with React 19 and Vite (frontend), Bash (`deploy/app`), HCL with OpenTofu 1.10.6 (infrastructure)

**Primary Dependencies**:

- **Existing**: FastAPI, SQLAlchemy and Alembic, DuckDB, Pydantic settings, structlog.
- **New runtime**: `boto3`. **New dev**: `jsonschema`. **Host**: `docker.io`, `docker-compose-v2`, `amazon-ecr-credential-helper` (Ubuntu archive).
- **Images**: `python:3.12-slim-bookworm`, `postgres:18`, `caddy:2`, `node:20` (build stage), all pinned by digest. `postgresql-client-18` comes from PGDG.

**Storage**:

- Postgres 18 (user data, unchanged schema).
- Pricing Parquet, read-only, from a local root or S3 through a local cache.
- S3 for backups and the operation lock.
- ECR for release images (base stack).
- SSM Parameter Store for the allowlist, the owner password and the TLS root.

**Testing**: pytest (unit, integration and contract, with a fake S3 store; no network), vitest, `tofu test` with mocked providers, shellcheck, a Docker build check, and the quickstart scenarios C–I as the real-account acceptance run.

**Target Platform**: AWS `us-east-1`, EC2 `t4g.small` (arm64), Ubuntu 24.04 LTS, Docker Compose v2. Locally: macOS arm64, with or without Docker.

**Project Type**: web application (`backend/` and `frontend/`), plus deployment assets (`infra/`, `deploy/`, `compose*.yaml`).

**Performance Goals**:

- Bring-up under 10 minutes (SC-001).
- A new snapshot active within one check interval, 300 s (SC-007).
- No failed requests during a switch.
- At most one download per snapshot revision per host (SC-005).

**Constraints**:

- About $0.30 per month while down (mostly ECR storage), and about $17.9 per month for 24/7 app use (research R3).
- 2 GiB RAM: DuckDB is capped at 512 MB, and Postgres uses `shared_buffers=128MB`.
- No inbound access except 443 from the allowlist.
- No secrets in images, the repo, state or logs.
- The repo is public.

**Scale/Scope**: a single owner, one environment (`prod`) at first. A snapshot is about 145 MB across 7 regions and 5 tables. User data is in the megabytes.

**Unknowns**: none left open. Two items are decided but must be **measured** before acceptance: `t4g.small` memory headroom (R3), and whether `workflow_dispatch` inputs are publicly visible (R13).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Assessment | Status |
|---|---|---|
| I. Vendor data is the source of truth | Prices still come only from the pipeline's Parquet, now located by its manifest. Checksums are verified for S3 copies. Nothing is estimated or hard-coded. The test fixture is rebuilt from real rows (R15). Because a date can now have several revisions, price and catalog responses carry `snapshot_revision` next to `snapshot_date`, so every price stays traceable to one dataset version (FR-059, added after `/speckit-analyze` finding C1). | PASS |
| II. Vendor data and user data stay separate | Backups contain only Postgres user data. The pricing cache is a separate read-only directory. The pipeline never touches Postgres. | PASS |
| III. Provider-aware naming | The reader, cache paths and settings are keyed by provider (`<root>/aws/…`, `cache/aws/…`). `PRICING_DATA_URI` replaces the AWS-named directory setting. No multi-provider code paths are built. | PASS |
| IV. Typed frontend/backend contract | The changed `system-info` and `/health`, the new `pricing-snapshot/check`, and the added `snapshot_revision` fields use Pydantic models, and TS types are regenerated. The existing `api-contract-drift` job gates it. | PASS |
| V. Test-first | Test-first: manifest selection and validation, path validation, cache verify-and-swap and clean-up, query file lists (DuckDB), restore and backup verification and retention (Postgres read/write of user data), and the `db-init` decision logic. Infrastructure behavior is covered by `tofu test` written with the stacks. The orchestration script is thin glue: shellcheck plus quickstart scenarios. | PASS (with the task order enforcing it) |
| VI. Simplicity and YAGNI | Each new piece maps to a spec requirement (see the inventory). Simpler alternatives were chosen where they exist: on-instance timers over a Lambda watchdog, SSM over a secrets service, one script and one deploy workflow, no separate operate role, no Spot, no load balancer, no NAT. ECR was chosen over the simpler public GHCR for consistency with the pipeline, a stated owner preference recorded in research R5. | PASS |
| Stack constraints | The application stack is unchanged (React/Vite/TS, FastAPI, Postgres, DuckDB over Parquet). S3 holds the *same* vendor Parquet and file backups, so it is not a new application datastore. Docker, Compose, OpenTofu and AWS are deployment tooling the spec fixes, not application stack changes. No amendment needed. | PASS |
| Quality gates | Pricing and DuckDB changes come with tests. API changes keep types in sync. Review checklist items I–III and VI are addressed above. | PASS |

**Post-design re-check (after Phase 1)**: still PASS. The design added no new datastore, no new API style and no speculative abstraction. The storage adapter has exactly two implementations, `local` and `s3`, both used now.

## Project Structure

### Documentation (this feature)

```text
specs/018-app-cloud-deployment/
├── plan.md               # This file
├── research.md           # Phase 0: decisions R1–R17
├── data-model.md         # Phase 1
├── quickstart.md         # Phase 1: validation scenarios A–I
├── contracts/
│   ├── configuration.md  # settings, script inputs, env files
│   ├── app-cli.md        # deploy/app and the app/release/oidc-subject workflows
│   ├── ops-cli.md        # in-image ops commands
│   ├── admin-api.md      # system-info changes, manual check endpoint
│   └── infrastructure.md # stacks, deploy role permissions, required tofu tests
├── checklists/requirements.md
└── tasks.md              # Phase 2 (/speckit-tasks)
```

### Source code (repository root)

```text
backend/
├── Dockerfile                          # NEW: python slim + uv sync + postgresql-client-18 (PGDG)
├── pyproject.toml                      # + boto3; dev + jsonschema
├── src/
│   ├── config.py                       # PRICING_DATA_URI & co.; refuses AWS_PRICING_PARQUET_DIR
│   ├── main.py                         # monitor uses the new snapshot service; DuckDB limits; typed /health with pricing state
│   ├── api/admin_system.py             # new system-info shape + POST pricing-snapshot/check
│   ├── api/calculate.py, api/catalog.py# + snapshot_revision in responses (FR-059)
│   ├── models/schemas.py               # SystemInfoOut, HealthOut, snapshot_revision fields
│   ├── pricing_data/
│   │   ├── storage.py                  # NEW: local + S3 adapters (missing/AccessDenied → None)
│   │   ├── manifest.py                 # NEW: Pydantic models + validation (pure)
│   │   ├── snapshot_cache.py           # NEW: verify-then-rename cache, clean-up (pure decisions)
│   │   ├── active_snapshot.py          # REWRITTEN: selection from pointer/pin, monitor state
│   │   ├── snapshot.py                 # ActiveSnapshot value object: files(), regions()
│   │   ├── pricing.py, catalog.py      # file lists from the active snapshot (no part-0 paths)
│   │   ├── regions.py, icon_coverage.py# manifest-based regions / previous snapshot
│   └── ops/                            # NEW: python -m src.ops …
│       ├── __main__.py                 # argument parsing, JSON result line, exit codes
│       ├── db_init.py, backup.py       # restore/verify/retention, owner password
│       ├── backup_store.py             # file:// and s3:// backup objects
│       ├── tls.py, health.py, alerts.py
├── scripts/build_test_pricing_fixture.py  # writes new layout + real manifests
└── tests/
    ├── fixtures/pricing_parquet/       # REBUILT: aws/parquet/…, aws/manifests/…
    ├── fixtures/manifests/             # NEW: hand-made edge-case manifests
    ├── fixtures/contracts/             # NEW: vendored latest/manifest schemas (+ source commit)
    ├── unit/   test_manifest.py, test_snapshot_selection.py, test_snapshot_cache.py,
    │           test_storage.py, test_config_data_source.py, test_backup_retention.py
    ├── integration/ test_db_init_restore.py, test_backup_roundtrip.py,
    │           test_pricing_from_manifest.py (+ existing pricing tests on the new fixture)
    └── contract/ test_manifest_schema_compat.py, test_admin_system_info.py, test_health.py,
                test_admin_snapshot_check.py (+ snapshot_revision in test_calculate.py, test_catalog.py)

frontend/
├── Dockerfile.web                      # NEW: node build stage → caddy image with dist + Caddyfile
├── Caddyfile                           # NEW: tls internal w/ provided root, /api → backend
└── src/components/admin/SystemInformationSection.tsx, src/components/workspace/PricingPanel.tsx
    (revision label) (+ generated schema.d.ts)

compose.yaml                            # NEW: web, backend, db, db-init, tls-init, ops (profile)
compose.local.yaml                      # NEW: local override (build, bind mounts, :8443)

deploy/
├── app                                 # NEW: up/down/status/allow/cert/ami-latest/backup-now
└── host/                               # NEW: cloud-init template, systemd units (timers)

infra/
├── base/                               # NEW: roles, instance role/profile, ECR repos, backup bucket,
│   └── tests/                          #      log group, topic, allowlist param (+ tofu tests)
├── instance/                           # NEW: VPC…instance, user-data from deploy/host
│   └── tests/
└── envs/prod.tfvars, prod.backend.hcl  # NEW (no secrets, no IPs)

.github/workflows/
├── ci.yml                              # pinned SHAs; + fixture env; + tofu/shellcheck/docker jobs; PR plan
├── release.yml                         # NEW: v* → ECR arm64 images (release role per env; skips existing tags)
├── app.yml                             # NEW: up/down/status/allow/backup-now
└── oidc-subject.yml                    # NEW

docs/
├── configuration.md                    # updated settings
└── deployment.md                       # NEW: runbook (one-time setup vs routine; FR-046, FR-054)
```

**Structure decision**: keep the existing `backend/` and `frontend/` web-app layout. Deployment assets go in three top-level folders by lifecycle:

- `infra/`: what OpenTofu manages.
- `deploy/`: what operators run, and what the host runs.
- `compose*.yaml`: what runs the containers, shared by the cloud and the laptop.

The ops CLI lives in the backend package, so it reuses settings, the ORM metadata and logging, and it ships in the image the instance already pulls.

## Key flows

**Bring-up** (`deploy/app up`, research R11):

1. Preflight and take the lock.
2. Resolve the release to digests.
3. Make sure the TLS root exists.
4. `tofu plan -out` the instance stack. If the plan replaces or destroys a running `aws_instance`, for any reason (release digests, AMI, `db_init_args`), take a `redeploy` backup and verify it (FR-029).
5. `tofu apply` that saved plan.
6. On the instance, cloud-init starts Compose: `tls-init`, then `db` healthy, then `db-init` (restore or fresh, migrate, owner password), then `backend` and `web`.
7. SSM `ops health --wait` returns a terminal status.
8. Send the notice, then unlock.

**Teardown**: lock, then SSM (stop `web` and `backend`, `ops backup --kind teardown` must report verified), then `tofu destroy`, then confirm, then unlock.

**Snapshot check** (every interval and on demand):

1. Read the pointer or the pin.
2. Validate the manifest.
3. If it isn't the active snapshot, use it in place (local) or fetch, verify and rename (S3).
4. Swap the active object.
5. Clean up the cache, refresh the latest-run summary, and run the icon analysis if the snapshot switched.

## Configuration inventory (FR-058)

This is everything this feature adds that someone must configure, store, schedule, grant or keep.

| Kind | Item | Needed by |
|---|---|---|
| **Backend settings** (new) | `PRICING_DATA_URI`, `PRICING_CACHE_DIR`, `PRICING_CACHE_MAX_BYTES`, `PRICING_CACHE_KEEP`, `DUCKDB_MEMORY_LIMIT`, `DUCKDB_THREADS` | FR-001, FR-009–FR-011; R3 memory |
| | `BACKUP_URI`, `BACKUP_KEEP`, `OWNER_PASSWORD_PARAMETER`, `ALERT_TOPIC_ARN`, `UPTIME_ALERT_HOURS`, `UPTIME_ALERT_REPEAT_HOURS`, `APP_ENVIRONMENT`, `APP_RELEASE` | FR-021–FR-026, FR-044, FR-014 |
| | `TLS_ROOT_DIR` (local packaged stack only: read the root from a directory instead of SSM) | Story 8, FR-037 |
| **Backend settings** (removed) | `AWS_PRICING_PARQUET_DIR` | FR-004 |
| **Packaged-stack variables** (Compose and cloud-init, not backend settings) | `BACKEND_IMAGE`, `WEB_IMAGE`, `PUBLIC_ADDRESS`, `HTTPS_PORT`, `DB_INIT_ARGS`, `LOG_GROUP`, `AWS_REGION`; locally `LOCAL_DATA_ROOT` in `.env.local` | FR-019, FR-023, FR-037, FR-043, Story 8 |
| **`deploy/app` and `ops` flags** | `--new-root`, `--break-lock`, `--force-without-backup` (FR-031's named override), `--backup`, `--release`; `db-init --allow-default-admin-password` (local only) | FR-037, FR-030, FR-031, FR-023, FR-057, Story 8 |
| **Host state** | `/var/lib/app/last-uptime-alert` (repeat-interval state) and the read-only `/host/proc/uptime` mount on `ops` | FR-044 |
| **Stored items** (SSM, per env) | `allowlist`, `owner-password`, `tls/root-key`, `tls/root-cert` | FR-036, FR-024, FR-037 |
| **Stored items** (S3, per env) | backup bucket (`<env>/db/`, `locks/`) | FR-025, FR-030 |
| **Stored items** (other) | log group, SNS topic and email subscription, two ECR repositories (base stack) | FR-043, FR-044, FR-018 |
| **Scheduled jobs** | 2 systemd timers on the instance (backup every 6 h, uptime check every 30 min) | FR-025, FR-044 |
| **Permission sets** | `plan`, `release` and `deploy` roles per env; the instance role (including ECR pull) | FR-049, FR-042 |
| **Separately managed resources** | the base stack (applied by hand), the instance stack (applied by `deploy/app`) | FR-032, FR-056 |
| **Pinned versions to maintain** | AMI ID per env, base image digests, Action SHAs, OpenTofu, provider lock hashes, the PGDG key fingerprint | FR-053 |
| **One-time manual steps** | OIDC subject template, GitHub environment and secrets, base-stack apply, confirming the email subscription, the owner password parameter, first allowlist entry, the `v*` tag ruleset, the `main` ruleset, installing the root on devices | FR-046 |
| **GitHub configuration** | secrets `AWS_ROLE_PLAN_<ENV>`, `AWS_ROLE_DEPLOY_<ENV>` and `AWS_ROLE_RELEASE_<ENV>`; variables `AWS_REGION`, `AWS_PLAN_ENABLED` and `RELEASE_ENVIRONMENTS`; environment `<env>`; `v*` and `main` rulesets | FR-049–FR-050 |
| **Laptop tools** | AWS CLI v2, OpenTofu, `openssl`, `jq` (for `deploy/app`); Docker (only for the local packaged stack) | FR-027, Story 8 |

**Deliberately not added** (simpler options chosen): a Lambda watchdog, Secrets Manager, a load balancer, NAT, Elastic IP, Spot, a third CI role, separate workflows per action, a separate operate role, a stored database password, a custom AMI build, and in-place release upgrades.

## Spec adjustments made during planning

- **FR-049** now names three purposes: previewing changes, publishing release images, and making changes. Research R2 explains why there is no separate "operate" role.
- **Registry**: ECR, at the owner's request (2026-10-02), for consistency with the pipeline. Research R5 records the trade-off against public GHCR.
- **After `/speckit-analyze` (2026-10-02)**:
  - FR-059 added: price and catalog responses carry the snapshot revision (constitution I).
  - FR-028: health no longer logs in with the owner password, which the owner can change in the app.
  - FR-029: any replacement of a running instance is preceded by a verified backup, detected from the plan, not from the release tag.
  - FR-038: `status` also sends the address notice, because the address is masked in GitHub logs.
  - FR-011 and SC-006: the clean-up rule is made precise (excess is removed at the next check).
  - FR-056: the "clear message" comes from the failing lookup plus the runbook check, instead of `precondition` blocks that cannot run when a lookup fails.
  - The PR preview stays limited to `infra/instance`. Previewing `infra/base` would need wider read permissions on the `plan` role. Base changes are applied by hand by the owner, who sees the plan then.

## Risks

| Risk | Mitigation |
|---|---|
| `t4g.small` memory is too small for DuckDB plus Postgres | Measured before acceptance (quickstart). Swap file plus DuckDB limit. The fallback is a recorded spec change, not a silent swap. |
| Missing AWS permissions are found one at a time (pipeline lesson) | Permission table in [contracts/infrastructure.md](./contracts/infrastructure.md), `tofu test` assertions, and a real `up`/`down` before acceptance (FR-045). |
| Existing auth is weak on a reachable host (R17) | Allowlist plus HTTPS. Owner password from a secret on a fresh database. A follow-up feature for real sessions is recommended. |
| A release isn't in a new environment's registry | Preflight names the missing tag. Re-running `release.yml` for that tag is safe because existing images are skipped. |
| A tag push can reach AWS | The `release` role can only push to two repositories, and a ruleset limits `v*` tag creation to the owner. |
| `workflow_dispatch` inputs may be publicly visible | Verification task (R13). Allowlist changes can be made from the laptop. |

## Complexity Tracking

No constitution violations. The table is not needed. Complexity is tracked in the [Configuration inventory](#configuration-inventory-fr-058) as FR-058 requires.
