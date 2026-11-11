# Development guide

How to run, test and change the app on a laptop. For settings see
[configuration.md](configuration.md); for AWS see [setup.md](setup.md) and [operations.md](operations.md).

## Contents

- [Tools](#tools)
- [Backend](#backend)
- [Frontend](#frontend)
- [Tests](#tests)
- [The production stack on a laptop](#the-production-stack-on-a-laptop)
- [Standard architectures](#standard-architectures)
- [Making a change](#making-a-change)

## Tools

- Python 3.12 or later with [uv](https://docs.astral.sh/uv/), Node.js with npm.
- Postgres 18 (`brew install postgresql@18 && brew services start postgresql@18`).
- **The Postgres 18 client tools on `PATH`**, for the backup and restore tests:

  ```bash
  export PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH"   # add to your shell profile
  ```

  Without them those tests skip without failing, and only CI runs them. Restore bugs then
  show up only on a real bring-up.
- Pricing data: a pipeline storage root from
  [cloud-pricing-data-retrieval](https://github.com/grp3d/cloud-pricing-data-retrieval), or
  the small fixture committed in `backend/tests/fixtures/pricing_parquet`.

## Backend

FastAPI, with DuckDB queries over the pricing Parquet and Postgres for user data (`backend/`).

```bash
cd backend
createdb cloud_pricing_dev
createdb cloud_pricing_test          # for the tests
uv sync --extra dev
source .venv/bin/activate
alembic upgrade head
```

Set `PRICING_DATA_URI` in `backend/.env` (template: `backend/.env.example`). It's the only
required setting; every setting is listed in [configuration.md](configuration.md).

From the repo root:

```bash
bin/start_back.sh       # uvicorn on :8000 with --reload, against cloud_pricing_dev, logging to backend_<pid>.log
```

The live OpenAPI schema is at `http://localhost:8000/openapi.json`.

## Frontend

React, Vite and TypeScript with Tailwind and shadcn/ui (`frontend/`).

```bash
(cd frontend && npm install)
bin/start_front.sh      # from the repo root: Vite on :5173; /api is proxied to the backend on :8000
```

The request and response types are generated from the backend's OpenAPI schema, never written
by hand:

```bash
npm run generate-api-types   # backend running on :8000
npm run check-api-types      # fails if the checked-in types are out of date (a CI check)
```

## Tests

| What | Command | Needs |
|---|---|---|
| Backend | `cd backend && uv run pytest` | Postgres with `cloud_pricing_test` migrated; the Postgres 18 client tools for the backup and restore tests |
| Backend lint | `uv run ruff check src/ tests/` | |
| Frontend unit | `cd frontend && npm test` | |
| Frontend lint and build | `npm run lint`, `npm run build` | |
| End-to-end | `npm run test:e2e` | `npx playwright install chromium` once; Postgres (it creates its own `cloud_pricing_e2e`) |

- **Backend:** the tests use a real Postgres database and real pricing Parquet, not mocks.
  `tests/conftest.py` points `PRICING_DATA_URI` at the committed fixture unless you set it, so
  no network is needed. Set `TEST_DATABASE_URL` to use a database other than
  `cloud_pricing_test`.
- **The pricing fixture** (`backend/tests/fixtures/pricing_parquet/`) is a small exact subset
  of the pipeline's data: one snapshot per provider, holding only the SKUs the tests use. Each
  provider folder has a README. After a test starts depending on a new AWS SKU, add it to
  `SEED_SKUS` and rebuild:

  ```bash
  uv run python scripts/build_test_pricing_fixture.py --source-uri file:///path/to/DATA/pipeline
  ```
- **Pipeline contracts** (`backend/tests/fixtures/contracts/`) are copied from the pipeline
  without changes; `tests/contract/test_manifest_schema_compat.py` checks the app still reads
  them.
- **End-to-end:** Playwright runs the real app in headless Chromium against its own backend
  (port 8100), a fresh database and the pricing fixture (`frontend/e2e/start-backend.sh`). It
  leaves a running dev setup alone.
- Don't run a formatter over whole folders: many files predate `ruff format`, and it would
  rewrap unrelated lines. Format only what you change.

## The production stack on a laptop

The same Compose stack as the cloud, with local data and backups and no AWS. Use it to check
packaging, backups and restores before a release.

```bash
deploy/app cert local --create              # once: a local TLS root in ./.local-tls (trust it)
cp .env.local.example .env.local            # once: set LOCAL_DATA_ROOT
docker compose --env-file .env.local -f compose.yaml -f compose.local.yaml up --build
```

Open `https://localhost:8443` and log in as `Admin`. A fresh local database keeps the default
Admin password (see the comment in `.env.local.example`); change it in the app. `LOCAL_DATA_ROOT` can be the committed fixture,
`backend/tests/fixtures/pricing_parquet`. With `dc` standing for
`docker compose --env-file .env.local -f compose.yaml -f compose.local.yaml`:

- Back up: `dc run --rm ops backup --kind manual` (files appear in `./.local-backups`).
- Restore check: `dc down -v` (wipes the database volume), then `dc up`: `db-init` logs
  `"db": "restored"`. Restoring a backup from the previous release this way also tests its
  migrations against real data.
- Health: `dc run --rm ops health --wait 60`.

## Standard architectures

Migration `0005_standard_architectures` seeds four public, Admin-owned architectures from
`backend/src/db/seed/standard_architectures.json`, once per database. If the Admin deletes or
renames one, it isn't recreated. The seed holds resolved `service_code`/`sku` references, so
the migration needs no pricing data.

The seed and its report (`standard_architectures_report.md`) are generated; don't edit them by
hand. To change what's seeded, edit the rules in
`backend/scripts/standard_architectures/match_rules.py` (one rule per usage figure in
[`docs/brief/common_aws_architectures.md`](brief/common_aws_architectures.md)) and re-run the
resolver against real pricing data:

```bash
cd backend
uv run python scripts/resolve_standard_architectures.py [--data-uri file:///path/to/DATA/pipeline]
```

It uses the latest snapshot; pin another with `ACTIVE_SNAPSHOT_DATE=YYYY-MM-DD`. Check the
report for figures left out and SKUs flagged as tiered, then rebuild the test fixture against
the same snapshot (it reads the seeded SKUs):

```bash
uv run python scripts/build_test_pricing_fixture.py --source-uri file:///path/to/DATA/pipeline \
    --snapshot-date YYYY-MM-DD
```

A database that has already run `0005` keeps its seed. To bring back a standard architecture
the Admin deleted, import `standard_architectures.json` on the Admin row of the Admin tab.

## Making a change

- **Features** go through Spec Kit: `/speckit-specify`, `/speckit-clarify`, `/speckit-plan`,
  `/speckit-tasks`, `/speckit-implement`, on a `0NN-short-name` branch. The design lives in
  `specs/0NN-*/`. The project's rules are in `.specify/memory/constitution.md`.
- **Docs:** a change updates the matching page in `docs/` and adds a line to
  [CHANGELOG.md](../CHANGELOG.md). The README is a fixed orientation page; it changes only when
  the repo's shape or the getting-started steps change.
- **Commits** use [Conventional Commits](https://www.conventionalcommits.org/), for example
  `feat(021): …`, `fix(ops): …`, `docs: …`.
- **Releases:** merge to `main`, let CI pass, then tag `v0.X.Y` and run `up`. See
  [operations.md](operations.md#releasing-a-new-version).
