# Implementation Plan: GCP and Azure Providers, Trends Page, Saved Preferences and Diagram Arrows

**Branch**: `019-gcp-azure-providers-trends` | **Date**: 2026-11-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/019-gcp-azure-providers-trends/spec.md`

## Summary

This feature enables GCP and Azure in the workspace, adds a first Trends page (a SKUs Changed chart and Biggest Movers lists), stores general preferences on the server, and adds arrow styles and branching connectors to the diagram.

**Approach**:
- **Snapshots**: the AWS-only snapshot monitor becomes one monitor per provider.
- **Shared request shapes**: each provider gets a `PricingProvider` adapter behind the existing request shapes. The AWS adapter wraps today's code; the one deliberate change is that AWS tiered prices are now applied by tier.
- **Tiered prices**: one shared graduated-tier function for all three providers (research R8).
- **Trends data**: built from a small, rebuildable **price change log** derived from consecutive weekly snapshots, kept on local disk and not in Postgres.
- **Preferences**: a typed JSON row per user.
- **Connectors**: two new columns and a branch table.

See [research.md](./research.md) for every decision.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.6 with React 18.3 (frontend)

**Primary Dependencies**:
- Backend: FastAPI, Pydantic v2, SQLAlchemy 2 with Alembic, DuckDB.
- Frontend: Vite, @tanstack/react-query, @xyflow/react, shadcn/radix.
- New: **Recharts** for the Trends charts (research R14).

**Storage**:
- PostgreSQL: user-defined data, including new preferences, category rules, connector arrows and branches.
- Read-only Parquet per provider, through manifests, local or on S3.
- Derived price history: local Parquet under `PRICING_HISTORY_DIR` (persistent, default `~/.cloud-pricing/history`, outside the snapshot cache).

**Testing**: pytest (unit, contract, integration, against real Postgres via the existing helpers), Vitest with Testing Library, and `npm run check-api-types`.

**Target Platform**: The existing single Linux instance (2 GiB, feature 018) and local development.

**Project Type**: Web application (`backend/` + `frontend/`).

**Performance Goals**:
- The Trends page shows the chart and movers within 3 seconds for the default selection (SC-004).
- Catalog search for Azure and GCP is as responsive as AWS today.

**Constraints**:
- DuckDB memory and threads stay within the existing caps (`DUCKDB_MEMORY_LIMIT` 512 MB).
- The cache holds three active snapshots within `PRICING_CACHE_MAX_BYTES` (R2).
- The history backfill processes one snapshot at a time.
- No price is estimated, converted or shown as 0 when missing (Principle I).

**Scale/Scope**:
- 3 providers, up to 52 weekly snapshots each.
- Snapshot sizes: AWS about 173k products per region; Azure about 33k items per region (including global); GCP about 18k SKUs per region.
- The same small user base as today.

## Constitution Check

*GATE: checked before Phase 0 research and again after Phase 1 design. Constitution v1.1.0.*

| Principle | Check | Result |
|---|---|---|
| I. Pricing Data Integrity | Prices are read as published. Null means "unavailable". No currency conversion. Every result names its provider, snapshot date and revision. Snapshots are validated per provider. History files record their source snapshots. | Pass |
| II. Data-Layer Separation | Preferences, category rules, connector arrows and branches are in Postgres (user-defined). Vendor data stays read-only. Derived price history is kept in rebuildable local files, **not** in Postgres. | Pass |
| III. Multi-Provider by Design | One request shape for every provider, with `PricingProvider` adapters behind it. Provider is a field everywhere. Adding a provider means adding an adapter. | Pass |
| IV. Type-Safe Contract | All new shapes are Pydantic models (preferences, `provider_options`, trends, connectors), with TypeScript generated from OpenAPI and `check-api-types` in CI. | Pass |
| V. Test-First | Test-first for: manifest validation per provider; each adapter's search, price, units and tiers against the reference lookups; the shared tier function, including the AWS tier fix; the change-log builder and counts; preference read/write; connector branch rules. | Pass (enforced in tasks) |
| VI. Simplicity & YAGNI | The adapters serve 3 real providers. The change log is the simplest store that fits 2 GiB and answers the chart and movers exactly. Two chart metrics were dropped after measuring real data (R11). No abstraction for further providers or LLM features. Branching connectors are isolated in the last phase so they can be cut. | Pass, with one justified item (below) |

**Post-design re-check** (after research, data model and contracts): still passes. The only new kind of store is the derived history files. They are justified below and fit Principles I and II because they are rebuildable, provenance-tagged and kept outside Postgres.

## Spec Amendments (approved 2026-11-03)

Planning found two places where the spec was wrong or misleading. Both were discussed and the spec was amended (spec Clarifications, session 2026-11-03):

1. **FR-008 (tiered prices)**: the spec said "the way AWS tiered prices are today", but AWS prices a tiered SKU from one arbitrary tier (an unsorted `LIMIT 1`). **Amended**: graduated tiers for AWS, Azure and GCP, applied per line, with free allowances only where published as a tier (research R8).
2. **FR-012, FR-015 (chart metrics)**: real AWS data showed about 1 price change among about 122,000 SKUs over 3 weeks, so median-based metrics are always 0%. **Amended**: the chart shows only SKUs Changed (counts up and down per week); Price Trend and Cumulative Change are dropped (research R11).

## Project Structure

### Documentation (this feature)

```text
specs/019-gcp-azure-providers-trends/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/api.md     # Phase 1 output
├── checklists/requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks, not created here)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── api/
│   │   ├── providers.py          # status per provider (contracts §1)
│   │   ├── regions.py            # ?provider=
│   │   ├── catalog.py            # ?provider=, kind
│   │   ├── sku_selections.py     # price types, provider_options
│   │   ├── connectors.py         # arrow_style, branches
│   │   ├── preferences.py        # NEW: /me/preferences
│   │   ├── trends.py             # NEW: /trends/series, /trends/movers
│   │   └── admin_system.py       # per-provider status + history
│   ├── pricing_data/
│   │   ├── active_snapshot.py    # one MonitorState per provider (R1)
│   │   ├── manifest.py           # per-provider tables, 1.1 fields, location paths
│   │   ├── snapshot.py           # provider-aware tables and locations
│   │   ├── snapshot_cache.py     # provider-aware clean-up (R2)
│   │   ├── providers/            # NEW (R3)
│   │   │   ├── base.py           # PricingProvider protocol, CatalogItem, PriceQuote
│   │   │   ├── registry.py
│   │   │   ├── aws.py            # wraps catalog.py / pricing.py unchanged
│   │   │   ├── azure.py
│   │   │   ├── gcp.py
│   │   │   └── units.py          # Azure / GCP unit tables (R7)
│   │   └── history/              # NEW (R10)
│   │       ├── builder.py        # comparable prices, week pairs, backfill
│   │       ├── store.py          # file layout, state.json
│   │       └── metrics.py        # SKUs Changed series, movers
│   ├── services/
│   │   ├── price_calculation.py  # dispatch to adapters; shared tiers; gcp machine parts
│   │   ├── architecture_service.py   # provider-aware validation; branch rules
│   │   ├── architecture_transfer.py  # optional new fields (R15)
│   │   ├── preferences_service.py    # NEW
│   │   └── categories.py             # NEW: rules → category for service keys
│   ├── models/orm.py, schemas.py
│   └── db/
│       ├── migrations/versions/0006_providers_trends_preferences.py
│       ├── migrations/versions/0007_service_category_seed.py
│       └── seed/service_categories.json
└── tests/
    ├── fixtures/pricing_parquet/{azure,gcp}/   # NEW small roots built from the 004 reference rows
    ├── fixtures/trends/                        # NEW multi-week roots + README with check queries
    ├── unit/   (adapters, units, tiers, manifest per provider, history builder, metrics, categories, preferences)
    ├── contract/ (providers, regions, catalog, selections, connectors, preferences, trends, admin)
    └── integration/ (azure/gcp assemble-and-price, provider isolation, backfill, export/import)

frontend/src/
├── pages/
│   ├── WorkspacePage.tsx         # provider-aware queries
│   └── TrendsPage.tsx            # NEW
├── components/
│   ├── layout/TopTabs.tsx        # enable Trends
│   ├── workspace/…               # provider buttons, region dialog, arrows UI
│   ├── providers/                # NEW: per-provider editor fields (aws, azure, gcp)
│   └── trends/                   # NEW: TrendsChartPanel, MoversPanel, selectors
├── lib/preferences.ts            # NEW: load, patch, retry queue, browser migration
└── api/generated/schema.d.ts     # regenerated
```

**Structure Decision**: Keep the existing web-application layout. Provider-specific code lives only in `backend/src/pricing_data/providers/` and `frontend/src/components/providers/`. Trends code lives in its own `history/` and `trends/` folders, so each user story can be built and tested on its own.

## Delivery Phases (input to `/speckit-tasks`)

1. **Foundations**:
   - per-provider monitor and manifest validation (R1, R2);
   - provider adapter protocol, with the AWS adapter wrapping today's code;
   - shared graduated-tier function, and the AWS tier fix with its updated tests;
   - migration `0006` (schema); the category seed follows in `0007` with US2.
   - **Gate**: all existing tests pass, apart from the listed AWS tier tests updated on purpose.
2. **US1 (P1), GCP and Azure**: adapters (search, units, tiers, price types, `provider_options`), API changes, Service Editor fields per provider, Admin per provider, export and import.
3. **US4 core (P3, but first-needed)**: preferences API and frontend preference store. It is moved ahead because Trends selections persist through it.
4. **US2 and US3 (P2), Trends**: category rules, history builder and backfill, SKUs Changed counts, Trends API, Trends page (chart and movers).
5. **US4 rest**: browser migration and moving the workspace settings.
6. **US5 (P3), arrows**: arrow style and reverse.
7. **US5, branching connectors**: last and separable (spec Assumptions).

## Complexity Tracking

| Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Derived price history files (`history/`) | The chart and movers need 52 weeks across 3 providers on a 2 GiB server | Reading historical snapshots per request needs far more memory and time. Storing aggregates in Postgres breaks Principle II. |
| `PricingProvider` adapter layer | Three providers now share one request shape (Principle III) | Branching on provider inside every function spreads provider oddities everywhere and puts the AWS code at risk. |
