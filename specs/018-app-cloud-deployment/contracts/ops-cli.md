# Contract: in-image `ops` commands

`python -m src.ops <command>` in the backend image, run by Compose services, by the systemd timers, or through SSM (`docker compose run --rm ops …`). Every command writes structured JSON logs (feature 017). Commands with a result also print **one JSON object on the last line of stdout**, which `deploy/app` parses.

| Command | Purpose | Result object |
|---|---|---|
| `db-init [--backup <id>] [--allow-default-admin-password]` | Restore the latest or named verified backup into an empty database, or initialize fresh. Then `alembic upgrade head`. On a fresh database, set the default Admin password from `OWNER_PASSWORD_PARAMETER`. A database that already has `alembic_version` is left as it is and only migrated. | `{"db": "restored"\|"fresh"\|"existing", "backup_id": str\|null, "alembic_revision": str, "row_counts": {...}}` |
| `backup --kind scheduled\|teardown\|redeploy\|manual` | `pg_dump -Fc`, list-check, upload dump then metadata, re-read size and checksum, mark verified, apply retention. On failure, alert. | `{"backup_id": str, "verified": bool, "bytes": int, "deleted": [ids]}` |
| `backups list` | List backups, newest first. | `{"backups": [{"id", "kind", "created_at", "verified", "app_release"}]}` |
| `fetch-tls --out /tls` | Write the env's root cert and key from SSM to a tmpfs volume for Caddy. | `{"root_fingerprint_sha256": str, "not_after": str}` |
| `health [--wait SECONDS]` | Wait for `db-init` to succeed and the backend's `/health` to answer. Check in the database that the default Admin account exists and is active. Check that `POST /api/v1/auth/login` answers `401` for a random, non-existent username. Read the pricing status from `/health` (see [admin-api.md](./admin-api.md)). It never uses the owner password, which the owner may have changed in the app (FR-028). | `{"healthy": bool, "db": str, "pricing": "ok"\|"unavailable", "pricing_reason": str\|null, "release": str}` |
| `uptime-alert` | Alert when host uptime passes `UPTIME_ALERT_HOURS`, then repeat every `UPTIME_ALERT_REPEAT_HOURS`. | `{"alerted": bool, "uptime_hours": float}` |
| `notify --message TEXT` | Publish to `ALERT_TOPIC_ARN` (or only log it when the setting is unset). | `{"published": bool}` |

**Exit codes**: `0` success. `3` precondition (no `BACKUP_URI`, backup not found, newer-release backup, missing owner password on a fresh database). `4` verification failed (row counts, checksum, `pg_restore --list`). `1` unexpected.

**Health gating**: `db-init` exiting non-zero blocks `backend` and `web` from starting (`depends_on: condition: service_completed_successfully`). `health` reports `healthy: false` with the `db-init` log tail.
