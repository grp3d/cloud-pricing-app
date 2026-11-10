#!/usr/bin/env bash
# Starts the backend for the end-to-end tests (playwright.config.ts runs this as a web server).
#
# A fresh database every run (E2E_DATABASE, default cloud_pricing_e2e), migrated to head, and
# the small pricing fixture committed in backend/tests/fixtures/pricing_parquet, so prices are
# exact and known in advance (see the fixture READMEs). Price history is off: Trends isn't tested
# here and it would write outside the repo.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
backend="$here/../../backend"
db="${E2E_DATABASE:-cloud_pricing_e2e}"
port="${E2E_BACKEND_PORT:-8100}"

# Homebrew's Postgres client, when present (as for the backend tests); CI has its own on PATH.
if [[ -d /opt/homebrew/opt/postgresql@18/bin ]]; then
  export PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH"
fi

dropdb --if-exists "$db"
createdb "$db"

cd "$backend"
export DATABASE_URL="${E2E_DATABASE_URL:-postgresql+psycopg://localhost/$db}"
export PRICING_DATA_URI="file://$backend/tests/fixtures/pricing_parquet"
export PRICE_HISTORY_ENABLED=false
export PRICING_HISTORY_DIR="${TMPDIR:-/tmp}/cloud-pricing-e2e-history"
export LOG_FORMAT=console
export LOG_LEVEL=WARNING

uv run alembic upgrade head
exec uv run uvicorn src.main:app --port "$port"
