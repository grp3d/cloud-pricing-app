# Data Model: On-Demand Cloud Deployment with Manifest-Driven Pricing Data

**Feature**: `018-app-cloud-deployment` | **Date**: 2026-10-02

This feature adds **no Postgres tables and no migrations**. Its entities are external documents read from the pipeline, files on disk and in S3, in-memory state, and infrastructure. The pipeline's documents are defined by its contracts. This file describes only how the app models and checks them.

---

## 1. Pricing data source

The location named by `PRICING_DATA_URI` (see [contracts/configuration.md](./contracts/configuration.md)).

| Field | Type | Rule |
|---|---|---|
| `kind` | `local` \| `s3` | `file://` or a plain absolute path gives `local`; `s3://` gives `s3`. Anything else stops startup. |
| `root` | path or `bucket[/prefix]` | `local`: the directory must exist. `s3`: not checked at startup, because the bucket can be unreachable and the app still starts. |
| `provider` | `aws` | Fixed for now. All keys are `<root>/<provider>/…` (FR-015). |

**Operations**: `get(key) → bytes | None` (missing, `AccessDenied` and 404 all become `None`), `list_manifest_dates() → [date]`, and `file_path(key)` (`local`) or `download(key, dest, expected_bytes, expected_sha256)` (`s3`).

## 2. Latest pointer

This is the pipeline's `latest.schema.json`. The app models it as a strict Pydantic model.

| Field | Used for |
|---|---|
| `manifest_version` | Major must be `1` |
| `provider` | Must equal the source's provider |
| `snapshot_date`, `revision` | The manifest named by `manifest_path` must have this date and a revision of at least this value |
| `manifest_path` | Must match `^<provider>/manifests/<date>/manifest\.json$`. Read relative to the root |
| `run_id`, `updated_at` | Shown in the Admin tab |

## 3. Snapshot manifest

This is the pipeline's `manifest.schema.json`. The app keeps these fields:

| Field | Used for |
|---|---|
| `manifest_version` | Major must be `1`. Unknown optional fields are ignored for minor bumps (`extra="ignore"`) |
| `provider`, `snapshot_date`, `revision`, `run_id`, `created_at` | Identity and display |
| `status` | Must be `succeeded` to activate. `partial`, `failed` and `purged` are only *shown* (latest run) |
| `regions.requested/succeeded/failed[]` | Admin tab and the `missing_regions` issue |
| `run.pipeline_version`, `run.trigger`, `run.started_at/ended_at` | Admin tab |
| `tables.<t>.schema_version` | Must be in `SUPPORTED_SCHEMA_VERSIONS[t]` (initially `{1}` for all five) |
| `tables.<t>.regions.<r>.files[] {path, bytes, sha256, row_count}` | The **only** way data files are found |
| `purged` | Non-null means not usable |

**Validation (FR-006, FR-007).** These checks are pure functions and are written test-first. A manifest is **usable** only if every check passes:

1. The JSON parses into the model.
2. The `manifest_version` major is supported.
3. `status == "succeeded"` and `purged is null`.
4. All five tables are present, each with a supported `schema_version`.
5. Every `path` matches `^<provider>/parquet/<table>/snapshot_date=<D>/region=<r>/part-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}(-[0-9]+)?\.parquet$`, where `<table>` is the containing table key, `<D>` is the manifest's `snapshot_date`, and `<r>` is the containing region key.
6. No path is absolute or contains `..` or `\`.
7. When reached through the pointer: the date is equal and `revision ≥ pointer.revision`.

Any failure produces a `RejectedManifest(reason)`. Nothing is fetched, and the current snapshot stays active.

## 4. Cached snapshot (S3 source only)

The directory `PRICING_CACHE_DIR/<provider>/<date>-r<revision>/` holds the manifest's files at their manifest paths, plus `cache-entry.json`.

| Field (`cache-entry.json`) | Type |
|---|---|
| `provider`, `snapshot_date`, `revision`, `run_id` | from the manifest |
| `manifest` | full manifest copy |
| `total_bytes` | sum of file bytes |
| `verified_at` | UTC timestamp |

**States and transitions:**

```text
            download to .tmp-<rand>/          all files match bytes+sha256
 (absent) ───────────────────────────► fetching ─────────────────────────────► verified
                                          │                                       │ selected
                                          │ any mismatch / 404 / disk full        ▼
                                          └──► (deleted, error reported)        active
                                                                                  │ newer snapshot activated
                                                                                  ▼
                                                                             superseded
                                                                                  │ at a later check than the one that superseded it
                                                                                  │ AND (beyond PRICING_CACHE_KEEP
                                                                                  │      OR over PRICING_CACHE_MAX_BYTES
                                                                                  │      OR manifest now purged)
                                                                                  ▼
                                                                              (deleted)
```

- **Verified** means a directory named `<date>-r<revision>` with a readable `cache-entry.json`. Only the atomic `rename()` creates one (FR-009).
- **Re-fetching**: a verified entry is never fetched again (FR-010). A higher revision of the same date is a different entry (FR-015).
- **Startup**: `*.tmp-*` directories are deleted.
- **Local sources** have no cache entries. The active snapshot's `base_dir` is the source root itself.

## 5. Active snapshot (in memory)

An immutable value object, replaced as a whole on a switch.

| Field | Type | Notes |
|---|---|---|
| `provider` | str | `aws` |
| `snapshot_date` | str | `YYYY-MM-DD` |
| `revision` | int | |
| `manifest` | Manifest | |
| `base_dir` | Path | the cache entry dir, or the local root |
| `pinned` | bool | from `ACTIVE_SNAPSHOT_DATE` |

**Methods:**

- `files(table, region) → list[str]`: absolute paths, from the manifest only.
- `regions(table) → set[str]`
- `common_regions() → set[str]`: regions present in all five tables.

**Monitor state** (replaces `ActiveSnapshotState`): `active`, `last_check_at`, `last_check_error`, `latest_run` (summary of the newest dated manifest, any status), `rejected` (date, revision, reason for the last refused manifest), `issues` (`missing_icon`, `missing_regions`) and `cache` (list of entries with state and size).

Removed: `waiting`, `marker_mtimes`, `logged_waiting`, and the `pinned_incomplete` issue kind.

## 6. Database backup

The objects `<BACKUP_URI>/<id>.dump` (pg_dump custom format) and `<BACKUP_URI>/<id>.json` (metadata, written last). The id is `<yyyymmddThhmmssZ>-<kind>-<release>`.

| Metadata field | Type | Rule |
|---|---|---|
| `id` | str | matches the object names |
| `kind` | `scheduled` \| `teardown` \| `redeploy` \| `manual` | |
| `created_at` | UTC timestamp | |
| `environment` | str | `prod`, `qa`, `dev` or `local` |
| `app_release` | str | e.g. `v1.4.0`, or `dev` |
| `alembic_revision` | str | head at backup time |
| `bytes`, `sha256` | int, hex | of the `.dump` |
| `row_counts` | `{table: int}` | for `users`, `architectures`, `collections`, `sku_selections`, `data_connectors` and any user-data table added later. The list comes from the ORM metadata, not hard-coded |
| `verified` | bool | `true` only after the uploaded object's size and checksum were re-read and `pg_restore --list` succeeded |

**Selection for restore**: the named id, or else the newest object with `verified: true`. A `.dump` without its `.json` is incomplete and ignored.

**Retention (FR-026)**: after a new backup is verified, delete verified backups beyond the newest `BACKUP_KEEP`, and incomplete ones older than 24 hours. The newest verified backup is never deleted.

**Restore verification (FR-022)**: after `pg_restore`, every `row_counts` entry must match `SELECT count(*)` exactly. An unknown `alembic_revision` (one not in this release's migration scripts) fails the restore before it starts.

## 7. Environment and deployment resources (infrastructure)

| Entity | Lives in | Survives "down" | Key attributes |
|---|---|---|---|
| Environment | `infra/envs/<env>.tfvars` | yes | name (`dev`, `qa`, `prod`), region, AMI ID, instance type, data bucket name, data read policy name |
| CI roles `plan`, `release`, `deploy` | base stack | yes | trust subjects (research R2) |
| Instance role and profile | base stack | yes | data read policy (from the pipeline), ECR pull on the env's repositories, backup bucket read/write, SSM params `/cloud-pricing-app/<env>/*` read, SNS publish, logs write, SSM core |
| Backup bucket `cloud-pricing-app-backups-<env>-<suffix>` | base stack | yes | private, SSE-S3, `db/` backups, `locks/` operation lock |
| Log group `/cloud-pricing-app/<env>` | base stack | yes | retention 14 days |
| Alert topic `cloud-pricing-app-alerts-<env>` | base stack | yes | email subscription |
| Allowlist parameter | base stack (value managed by `app allow`) | yes | list of `/32` or `/128` |
| TLS root (key and cert parameters) | created by `app up` the first time | yes | 5-year validity |
| Owner password parameter | created by the owner (runbook) | yes | SecureString |
| ECR repositories `cloud-pricing-app-{backend,web}-<env>` | base stack | yes | immutable tags, scan-on-push, keep the newest 5 tagged images. Tags resolve to digests at "up" |
| VPC, subnet, IGW, route table, security group, instance | instance stack | **no** | tags `environment=<env>`, `app=cloud-pricing-app` |
| Operation lock `locks/<env>.json` | backup bucket | exists only during an operation | `{action, by, started_at, run_url}` |

**Instance lifecycle** (the instance stack):

```text
 (down) ──app up──► provisioning ──cloud-init + db-init OK + /health OK──► up
   ▲                    │ any failure: "up" fails, stack stays; next up or down cleans it
   │                    ▼
   └──app down◄── failed
 up ──app down──► backing-up ──backup verified──► destroying ──► (down)
                      │ backup fails
                      └──► up (nothing destroyed, reason reported)
```

## 8. Allowlist entry

| Field | Rule |
|---|---|
| address | one IPv4 address (stored as `/32`) or IPv6 address (stored as `/128`). Ranges are refused |
| uniqueness | duplicates are ignored on add. Removing a missing entry is a no-op with a message |
| limit | up to 50 entries (security-group rule quota headroom) |
