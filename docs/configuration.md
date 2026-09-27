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
| `AWS_PRICING_PARQUET_DIR` | path | the local development data path | Root of the AWS pricing Parquet tables (`service_dim/`, `product_dim/`, `product_attribute/`, `region_dim/`, `price_fact/`), each partitioned by `snapshot_date=` and `region=`. Read-only. |
| `AWS_PRICING_REGION` | string | `us-east-1` | Legacy single-region default. Pricing is per collection region, except for the Price Change comparison, which reprices earlier selections in this region. |
| `SNAPSHOT_CHECK_INTERVAL_SECONDS` | integer ≥ 10 | `300` | How often the background check looks for a newer, fully written pricing snapshot. It also re-runs the icon-coverage analysis when the active snapshot changes. |
| `ACTIVE_SNAPSHOT_DATE` | date (`YYYY-MM-DD`) or unset | unset | Pins the pricing snapshot every lookup uses, e.g. to roll back from bad upstream data. The date must exist in all five tables or the server won't start. If it has no `_SUCCESS` markers, the server starts and the Admin tab shows a warning. |
| `CORS_ALLOWED_ORIGINS` | JSON list of strings | `["http://localhost:5173"]` | Browser origins allowed to call the API. |
| `CATALOG_SEARCH_DEFAULT_LIMIT` | integer ≥ 1 | `50` | Catalog search page size when a request doesn't specify one. Must not exceed the maximum. |
| `CATALOG_SEARCH_MAX_LIMIT` | integer ≥ 1 | `200` | The largest page size a catalog search may request. |
| `PASSWORD_HASH_ITERATIONS` | integer ≥ 100000 | `260000` | PBKDF2 iterations for newly set passwords. Existing hashes keep their own count, so changing this doesn't lock anyone out. |
| `LOG_LEVEL` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` | `INFO` | Server log level. |

## Pricing snapshots and `_SUCCESS` markers

The backend only switches to a pricing snapshot once the upstream job has finished writing it. It
treats a snapshot as finished when `<table>/snapshot_date=<date>/_SUCCESS` exists for all five
tables. The upstream job writes this marker as its last step, and must rewrite it (update its
modification time) when it updates a snapshot in place. The Admin tab's System Information section
shows the active snapshot, any snapshot still waiting, and why it's waiting.
