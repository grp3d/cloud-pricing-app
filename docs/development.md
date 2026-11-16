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
- [The agent](#the-agent)
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

Run `alembic upgrade head` again whenever you pull or switch to a branch with a new migration:
the backend won't start against a database that isn't at the code's latest migration, and says
so in one line.

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

**GCP and Azure (022).** Migration `0009_gcp_azure_standard_architectures` seeds the GCP and Azure
equivalents the same way, from `standard_architectures_gcp.json` and
`standard_architectures_azure.json` (skipping any the Admin already owns with the same name and
provider). Their rules are in `match_rules_gcp.py` and `match_rules_azure.py`: each rule names
the AWS component and figure it stands in for, and the shared usage formulas are in
`quantities.py`. Generate with:

```bash
uv run python scripts/resolve_standard_architectures.py --provider gcp    # or azure
```

It uses the provider's latest local snapshot, which must hold every region the rules use
(europe-west1 and westeurope included; the command stops if one is missing). Then rebuild the
small fixture those tests use, which holds only the seeded items:

```bash
uv run python scripts/build_provider_fixtures.py --source-uri file:///path/to/DATA/pipeline \
    --standard-architectures
```

The AWS seed was generated from the 2026-09-24 snapshot; to re-run it unchanged, pin
`ACTIVE_SNAPSHOT_DATE=2026-09-24`.

## The agent

The [agent](features/agent.md) is off by default. To try it locally with a free local model:

```bash
brew install ollama && ollama serve        # in another terminal
ollama pull llama3.1                       # any model that supports tool calling
```

Then, on the Admin page, open **Agent settings**: tick **Agent on**, keep the provider **Ollama**,
set the model to `llama3.1`, and save. (Or start the backend with `AGENT_ENABLED=true
AGENT_MODEL=llama3.1`.) Turn the agent on for a user in the user table, or use their 3 free
preview messages. For the hosted model, put `AGENT_ANTHROPIC_API_KEY=…` in `backend/.env`, choose
**Anthropic**, and enter both token prices. Every setting is listed in
[configuration.md](configuration.md#agent).

- **Tests never call a real model.** Every agent test uses the scripted model
  (`src/agent/clients/scripted.py`). The example conversations from the spec are in
  `backend/tests/agent_evals/cases/*.yaml`; the normal run plays each one with its script.
- **Checking real models** is a separate run, against the same cases and fixed checks (figures
  equal to the engine's to the cent, operations run, phrases present or absent, refusals, and
  for comparisons: each result row recalculated through the engine, match qualities, partial
  totals, and no result for a single price):

  ```bash
  cd backend
  AGENT_EVAL_MODELS="ollama:llama3.1,anthropic:claude-sonnet-5-5" uv run pytest -m live_model
  ```

  Since 025 the cases also check proposals: their kind and changes, figures equal to the
  engine's for the before and after states, nothing saved before Accept, and scripted user
  actions after the answer (`actions: [accept, undo, redo, manual_edit, undo_refused, reject]`),
  with the saved architecture checked after each. 025's cases (`gc-19` to `gc-28`) are checked
  live on Claude Haiku 5.5 only; other models may be run for information.

  It writes `backend/agent-eval-report.md` (not committed), with pass or fail per case and
  per check, for each model. A hosted model needs `AGENT_ANTHROPIC_API_KEY`, in the environment
  or in `backend/.env` (the same place the app reads it from). The comparison cases
  (`pricing: combined`) price against every provider's test fixture at once.
- **Budget for hosted-model runs.** Every case is several paid calls, and a full run of every
  case is about a dollar on Sonnet. Testing one change must stay under **$0.50** unless the
  person paying agrees to more first:
  - Iterate with the scripted cases and a local model (`ollama:…`, free). A hosted run confirms
    a change; it isn't for iterating.
  - Before a hosted run, give an estimate (which cases, which model, how many runs, calls and
    cost in USD, from the last report's calls and tokens per case) and get a yes. If the work
    then needs more than was approved, stop and give a new estimate.
  - Run only the cases the change affects (`-k "GC-12 or GC-13"`), once. Use the cheapest model
    that answers the question (Haiku before Sonnet). Run the full set only before a release or
    when asked.
  - At most two hosted runs per change. Fix wording or checks from the saved report, not by
    running again; never repeat runs to test stability.
  - If a run fails with an API error (credit, key, rate limit), stop: don't retry.
  - The run enforces the approved estimate. A paid model runs only with
    `AGENT_EVAL_APPROVED_USD` (the amount approved) and its price in `AGENT_EVAL_PRICES`, in USD
    per million tokens as the provider lists them:

    ```bash
    AGENT_EVAL_MODELS="anthropic:claude-haiku-5-5" AGENT_EVAL_APPROVED_USD=0.25 \
    AGENT_EVAL_PRICES="claude-haiku-5-5=<in>/<out>" AGENT_EVAL_MAX_CALLS=25 \
    uv run pytest -m live_model -k "GC-12 or GC-13"
    ```

    Before each paid call it checks what has been spent: if one more call at the run's average
    cost would go past the approved amount, or the run has made `AGENT_EVAL_MAX_CALLS` paid calls
    (default 30), the whole run stops and says why. It also stops on an API error. Local models
    are counted but never capped.
  - The report gives calls, input and output tokens, and cost for each case and each model, and
    what was spent against the approved amount.
- **End-to-end:** `e2e/agent.spec.ts` runs last, in its own Playwright project, because it
  switches the app-wide agent setting on (with the scripted model) and off again.

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
