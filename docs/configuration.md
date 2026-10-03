# Backend configuration

Every operational setting lives on `Settings` in `backend/src/config.py` (pydantic-settings). Each
one has a default that matches the app's normal local behavior. Any of them can be overridden by an
environment variable with the same name in upper case, or by a line in `backend/.env`. See
`backend/.env.example` for a commented template.

If a value is invalid (wrong type, out of range, not one of the allowed choices), **the server
refuses to start**, and the error names the setting.

| Environment variable | Type | Default | What it controls |
|---|---|---|---|
| `DATABASE_URL` | string | `postgresql+psycopg://localhost/cloud_pricing_dev` | Postgres connection for user data (architectures, collections, users). |
| `PRICING_DATA_URI` | `file:///abs/path`, `/abs/path` or `s3://bucket[/prefix]` | **required** | The pricing data pipeline's storage root (the folder that holds `aws/manifests/` and `aws/parquet/`), local or in S3. Snapshots are found only through its manifests. A local path must exist. Read-only. See [Pricing data](#pricing-data). |
| `PRICING_CACHE_DIR` | path | `<system temp>/cloud-pricing-cache` | Where verified copies of S3 snapshots are kept. Unused for a local source. |
| `PRICING_CACHE_MAX_BYTES` | integer ≥ 268435456 | `1073741824` (1 GiB) | Size limit of that cache. A snapshot bigger than this, or than the free disk space, is not activated, and the reason shows in the Admin tab. |
| `PRICING_CACHE_KEEP` | integer ≥ 0 | `1` | Cached snapshots kept besides the active one. Anything beyond this, over the size limit, or purged by the pipeline is deleted at the next check. |
| `DUCKDB_MEMORY_LIMIT` | DuckDB size, e.g. `512MB` | `512MB` | Memory cap for each pricing query. |
| `DUCKDB_THREADS` | integer ≥ 1 | `2` | Threads for each pricing query. |
| `AWS_PRICING_REGION` | string | `us-east-1` | Legacy single-region default. Pricing is per collection region, except for the Price Change comparison, which reprices earlier selections in this region. |
| `SNAPSHOT_CHECK_INTERVAL_SECONDS` | integer ≥ 10 | `300` | How often the background check looks for a newer snapshot, or a newer revision of the active one. It also re-runs the icon-coverage analysis when the active snapshot changes. |
| `ACTIVE_SNAPSHOT_DATE` | date (`YYYY-MM-DD`) or unset | unset | Pins the pricing snapshot every lookup uses, e.g. to roll back from bad upstream data. That date's manifest must exist and be `succeeded`, or the server won't start. |
| `CORS_ALLOWED_ORIGINS` | JSON list of strings | `["http://localhost:5173"]` | Browser origins allowed to call the API. |
| `CATALOG_SEARCH_DEFAULT_LIMIT` | integer ≥ 1 | `50` | Catalog search page size when a request doesn't specify one. Must not exceed the maximum. |
| `CATALOG_SEARCH_MAX_LIMIT` | integer ≥ 1 | `200` | The largest page size a catalog search may request. |
| `PASSWORD_HASH_ITERATIONS` | integer ≥ 100000 | `260000` | PBKDF2 iterations for newly set passwords. Existing hashes keep their own count, so changing this doesn't lock anyone out. |
| `LOG_LEVEL` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` | `INFO` | Minimum level of log records written. |
| `LOG_FORMAT` | `json` \| `console` | `json` | Log output format. `json` writes one JSON object per line with `timestamp`, `level` and `message`; `console` writes colored, readable lines for local development. Any other value stops startup. |

Removed: `AWS_PRICING_PARQUET_DIR`. If it is still set (in the environment or `backend/.env`), the
server refuses to start and names `PRICING_DATA_URI` as its replacement.

## Pricing data

The pricing data comes from the separate pipeline repository (`cloud-pricing-data-retrieval`),
in the storage layout its contracts define: each snapshot date has a **manifest** listing its data
files, and `aws/manifests/latest.json` names the newest `succeeded` snapshot. The layout is the
same in a local folder and in S3, so switching between them means changing `PRICING_DATA_URI` only
(plus read credentials for S3).

- **Which snapshot is used**: the one `latest.json` names, or the `ACTIVE_SNAPSHOT_DATE` pin. Only
  `succeeded` manifests with a supported contract version are used, and only the files they list
  are read. Data folders are never scanned.
- **Local source**: files are read where they are. No cloud account, credentials or network.
- **S3 source**: the active snapshot is copied once into `PRICING_CACHE_DIR`, each file checked
  against the manifest's size and checksum, and swapped in only when complete. Credentials come
  from the standard AWS chain (the instance role in the cloud, a profile on a laptop).
- **Updates**: the background check (and **Check now** in the Admin tab) switches to a newer
  snapshot or revision all at once. If anything is wrong — the source is unreachable, a manifest is
  invalid, a checksum fails — the current snapshot stays in use and the Admin tab says why.
- **No snapshot yet**: the server starts, login and saved architectures work, and pricing requests
  return "pricing data unavailable" until one appears.

### Converting the old layout

The old local layout (`<table>/snapshot_date=<date>/` folders with `_SUCCESS` markers) is no longer
read. Pointing `PRICING_DATA_URI` at it stops startup with this explanation. To get a supported
folder, either run the pipeline locally (it writes the new layout), or convert existing data with
the pipeline's history-upload command (`upload-history`, documented in that repository), then set
`PRICING_DATA_URI` to the folder it wrote.
