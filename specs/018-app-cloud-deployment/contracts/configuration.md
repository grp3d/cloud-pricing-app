# Contract: Configuration

Backend settings (environment variables, also read from `backend/.env`). Any invalid value stops startup and names the setting, as today. The default is what a developer gets with nothing set. "Cloud" is what cloud-init writes on the instance.

## Pricing data (replaces `AWS_PRICING_PARQUET_DIR`)

| Setting | Default | Cloud | Rule |
|---|---|---|---|
| `PRICING_DATA_URI` | **required** | `s3://cloud-pricing-data-<env>-<suffix>` | `file:///abs/path`, `/abs/path`, or `s3://bucket[/prefix]`. Points at the storage root, not at `aws/` and not at a table folder. A local path must exist. |
| `PRICING_CACHE_DIR` | `<tmp>/cloud-pricing-cache` | `/var/lib/app/pricing-cache` (a volume) | Used only for `s3://` sources. |
| `PRICING_CACHE_MAX_BYTES` | `1073741824` (1 GiB) | same | ≥ 268435456. |
| `PRICING_CACHE_KEEP` | `1` | same | ≥ 0. Snapshots kept besides the active one. |
| `SNAPSHOT_CHECK_INTERVAL_SECONDS` | `300` | same | Unchanged (≥ 10). |
| `ACTIVE_SNAPSHOT_DATE` | unset | unset | Unchanged meaning. The pinned date's manifest must be `succeeded`, or startup stops. |
| `DUCKDB_MEMORY_LIMIT` | `512MB` | `512MB` | DuckDB size string. |
| `DUCKDB_THREADS` | `2` | `2` | ≥ 1. |
| `AWS_PRICING_PARQUET_DIR` | — | — | **Removed.** If it is set, startup stops with: `AWS_PRICING_PARQUET_DIR was replaced by PRICING_DATA_URI (the pipeline storage root, e.g. file:///…/DATA/pipeline). See docs/configuration.md.` |

AWS credentials for `s3://` come from the standard chain: the instance role in the cloud, or a named profile or Roles Anywhere `credential_process` on a laptop. No setting names them.

## Database lifecycle and backups (ops commands; also read by the backend for display)

| Setting | Default | Cloud | Rule |
|---|---|---|---|
| `BACKUP_URI` | unset (backup and restore commands refuse to run) | `s3://cloud-pricing-app-backups-<env>-<suffix>/<env>/db/` | `file://` or `s3://`. |
| `BACKUP_KEEP` | `14` | `14` | ≥ 1. |
| `OWNER_PASSWORD_PARAMETER` | unset | `/cloud-pricing-app/<env>/owner-password` | Read only by `db-init` on a fresh database. If unset on a fresh database, `db-init` refuses unless `--allow-default-admin-password` is given (local only). |
| `ALERT_TOPIC_ARN` | unset (alerts are only logged) | from the base stack | SNS topic for backup failures, uptime and "up" notices. |
| `UPTIME_ALERT_HOURS` | `12` | `12` | ≥ 1. |
| `UPTIME_ALERT_REPEAT_HOURS` | `12` | `12` | ≥ 1. |
| `APP_ENVIRONMENT` | `local` | `<env>` | Shown in the Admin tab and in backup metadata. |
| `APP_RELEASE` | `dev` | release tag | Same. |
| `TLS_ROOT_DIR` | unset | unset | Local packaged stack only. When set, `fetch-tls` copies `root.crt` and `root.key` from this directory instead of reading SSM. |

## Packaged-stack variables (Compose and cloud-init; not backend settings)

| Variable | Cloud (written by cloud-init) | Local (`compose.local.yaml`, `.env.local`) | Used by |
|---|---|---|---|
| `BACKEND_IMAGE`, `WEB_IMAGE` | image by digest | built locally | every service |
| `PUBLIC_ADDRESS` | from IMDSv2 at boot | `localhost` | Caddy site address |
| `HTTPS_PORT` | `443` | `8443` | Caddy and the published port |
| `DB_INIT_ARGS` | empty, or `--backup <id>` | empty, or `--allow-default-admin-password` | `db-init` |
| `LOG_GROUP`, `AWS_REGION` | from the base stack and inputs | unused (`json-file` logging) | the `awslogs` driver |
| `LOCAL_DATA_ROOT` | — | path to a local pipeline root | the read-only `/data` mount |

## `deploy/app` and `app.yml` inputs

| Variable or input | Required | Rule |
|---|---|---|
| `APP_ENV` / `--env` / input `environment` | yes | `dev`, `qa` or `prod`. Never inferred. |
| `AWS_REGION` | yes | Never read from `~/.aws/config` (FR-048). |
| `AWS_PROFILE` | laptop only | Optional. The standard chain otherwise. |
| `--release` / input `release` | no | A `v*` tag. Default is the newest released tag with both images. |
| `--backup` / input `backup` | no | A backup id to restore instead of the newest. |
| input `address` | for `allow` | One IP. Masked in logs. |

## GitHub variables for releases

| Variable | Default | Rule |
|---|---|---|
| `RELEASE_ENVIRONMENTS` | `["prod"]` | JSON list of envs whose ECR repositories receive each release (used as the release workflow's matrix). Add an env here **before** tagging the release it will deploy. |

## Files under `infra/envs/` (committed, no secrets, no personal IPs)

`<env>.tfvars`: `environment`, `aws_region`, `ami_id`, `instance_type`, `root_volume_gib`, `data_bucket_name`, `data_read_policy_name`, `log_retention_days`, `backup_bucket_suffix`.

`<env>.backend.hcl`: the shared state bucket and region, with `key = "app/<env>/<stack>.tfstate"` passed per stack.

`TF_VAR_alert_email` is supplied when applying the base stack (`infra/base`), never committed.
