# Implementation Plan: Canvas Icon Layout, Active Pricing Snapshot & Configurable Settings

**Branch**: `016-canvas-icon-layout` | **Date**: 2026-09-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/016-canvas-icon-layout/spec.md`

## Summary

**Canvas**
- Service icons become 60px, placed 3 per row with 90px spacing.
- Icons are hand-placeable, with positions saved per browser.
- Icons can be dragged into any same-region box, which moves the service via a new `collection_id`
  on `PATCH /sku-selections/{id}`.
- The hover pop-up gains 15 labeled attribute lines and drops Operation.

**Two defect fixes**
- Errors are split by column.
- New top-level boxes are placed in view.

**Backend**
- An in-process **active snapshot** replaces the per-request "newest date" scan. A single asyncio
  background task maintains it: it switches only to dates with `_SUCCESS` in all five tables,
  supports a pinning override, and runs the icon-coverage analysis.
- The results are exposed to a restructured Admin tab (User Management; System Information and
  Issues) through `GET /admin/system-info`.
- Remaining hard-coded operational values move into the existing `pydantic-settings` `Settings`.

Details are in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12 (backend); TypeScript 5.6 / React 18 (frontend)

**Primary Dependencies**:
- Backend: FastAPI, Pydantic, `pydantic-settings` (already used), DuckDB, SQLAlchemy async.
- Frontend: Vite 5, `@xyflow/react` 12, TanStack Query 5, radix-ui, Tailwind 4.
- **No new dependencies.** The background task uses stdlib `asyncio`.

**Storage**:
- Parquet via DuckDB: read-only, plus directory listings for `_SUCCESS` markers.
- Postgres: no schema change. An existing column (`sku_selections.collection_id`) now changes when
  a service is moved.
- In-process memory: the active snapshot state and issues.
- Browser `localStorage`: icon positions.

**Testing**: pytest (unit + contract, test-first), Vitest + Testing Library,
`npm run check-api-types`.

**Target Platform**: A local FastAPI server in a single process, and modern desktop browsers.

**Project Type**: Web application (`backend/` + `frontend/`)

**Performance Goals**:
- The active-date lookup is an in-memory read: no filesystem scan per request.
- A snapshot check lists 5 tables × about 22 dates and finishes well under 1 s.
- The icon analysis is a single `service_dim` read.
- Dragging stays smooth (60 fps target) with up to about 30 icons per box.

**Constraints**:
- No persistence of monitoring state (Clarification Q4).
- Every setting's default must equal today's behavior.
- The CI fixture must gain `_SUCCESS` markers, or CI has no active snapshot.

**Scale/Scope**: 5 pricing tables, about 22 snapshot dates, 7 regions and about 250 service codes;
architectures with tens of services per box.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Status |
|---|---|---|
| I. Pricing Data Integrity | Strengthened: prices can no longer be computed from a half-written snapshot. One active date is used per request (FR-019), and results still carry `snapshot_date`. Moving a service between same-region boxes doesn't change any price. Nothing is estimated. | ✅ |
| II. Data-Layer Separation | Parquet stays read-only (the backend only lists folders and reads files). The only Postgres write is the user-defined `collection_id` change. Monitoring state and issues are in memory and never written to Postgres. The icon map is generated code/config, not vendor pricing data. | ✅ |
| III. Provider-Extensibility | The icon map and coverage analysis are AWS-named modules (`aws_service_icons.json`, `awsServiceIcons.ts`). The active-snapshot monitor takes the parquet directory and table list as parameters rather than hard-wiring AWS into shared abstractions. Adding another provider means another monitor instance, not a rewrite. | ✅ |
| IV. Type-Safe Contract | `SystemInfoOut`, `IssueOut`, `WaitingSnapshotOut` and `SKUSelectionUpdate.collection_id` are Pydantic models. `schema.d.ts` is regenerated, and `check-api-types` gates drift. | ✅ |
| V. Test-First | Written first: the snapshot selection and completeness logic, the override validation, region comparison, icon-coverage analysis, the SKU move endpoint (a Postgres write), the settings validation, and the pure frontend geometry modules (`iconLayout`, `newNodePlacement`). Presentational layout may be tested after. | ✅ |
| VI. Simplicity & YAGNI | No scheduler library, no new datastore, no persistence (explicitly deferred). It reuses `pydantic-settings`, `localStorage` patterns and the existing 503 mapping. One background task covers both checks. | ✅ |

**Post-Phase-1 re-check**: data-model.md and the contracts introduce nothing beyond the table
above. **Gate: PASS. No Complexity Tracking entries.**

## Project Structure

### Documentation (this feature)

```text
specs/016-canvas-icon-layout/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── api.md          # GET /admin/system-info; PATCH sku-selections collection_id
│   └── ui.md           # icons, drag, pop-up, error placement, new-box placement, Admin tab
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── scripts/
│   ├── generate_aws_service_icon_map.py         # + writes src/pricing_data/aws_service_icons.json
│   └── build_test_pricing_fixture.py            # + writes _SUCCESS per table/date
├── src/
│   ├── config.py                                # + cors, catalog limits, hash iterations, log level,
│   │                                            #   snapshot interval, active_snapshot_date
│   ├── main.py                                  # lifespan: startup check + background task; CORS/log from settings
│   ├── models/schemas.py                        # SystemInfoOut, IssueOut, WaitingSnapshotOut; SKUSelectionUpdate.collection_id
│   ├── api/admin_system.py                      # NEW: GET /admin/system-info
│   ├── api/sku_selections.py                    # move via collection_id
│   ├── api/catalog.py                           # limits from settings
│   ├── services/auth_service.py                 # iterations from settings
│   ├── services/architecture_service.py         # resolve active date once per request
│   └── pricing_data/
│       ├── active_snapshot.py                   # NEW: state, check_snapshots(), get_active_snapshot_date(), monitor loop
│       ├── icon_coverage.py                     # NEW: find_unmatched_services()
│       ├── aws_service_icons.json               # NEW (generated)
│       ├── snapshot.py                          # resolve_latest_snapshot_date removed; shared table list/helpers
│       ├── catalog.py, pricing.py, regions.py   # use active date
│       └── ...
├── tests/
│   ├── unit/test_active_snapshot.py             # NEW
│   ├── unit/test_icon_coverage.py               # NEW
│   ├── unit/test_settings.py                    # NEW
│   ├── unit/test_icon_map_consistency.py        # NEW
│   ├── contract/test_admin_system_info.py       # NEW
│   ├── contract/test_sku_selections.py          # + move cases
│   └── fixtures/pricing_parquet/**/_SUCCESS     # NEW (regenerated fixture)
├── .env.example                                 # NEW
docs/configuration.md                            # NEW

frontend/
├── src/
│   ├── lib/iconLayout.ts                        # NEW: geometry (ICON/GAP/rows, validity, nearest spot)
│   ├── lib/iconLayoutStorage.ts                 # NEW: per-browser icon positions
│   ├── lib/newNodePlacement.ts                  # NEW: findVisibleSlot
│   ├── lib/servicePopup.ts                      # + 15 attribute lines, − Operation, deduped summary
│   ├── lib/skuDetail.ts                         # summarizeAttributes({ exclude })
│   ├── components/workspace/ArchitectureDiagramPanel.tsx  # icon area, drag/drop, box widths, new-box placement
│   ├── components/admin/SystemInformationSection.tsx      # NEW
│   ├── pages/AdminPage.tsx                      # User Management + System Information sections
│   ├── pages/WorkspacePage.tsx                  # split action errors; move-service mutation
│   └── api/client.ts, api/generated/schema.d.ts # getSystemInfo, updateSkuSelection(collection_id)
└── tests/unit/
    ├── iconLayout.test.ts, iconLayoutStorage.test.ts, newNodePlacement.test.ts   # NEW
    ├── servicePopup.test.ts                     # updated
    ├── ServiceIconList.test.tsx                 # updated (60px, positions)
    ├── WorkspacePage.errors.test.tsx            # NEW (column-scoped errors)
    └── SystemInformationSection.test.tsx        # NEW
```

**Structure Decision**: the existing web-app layout. New pure logic goes into `frontend/src/lib/`
and `backend/src/pricing_data/`, following the one-concern-per-module convention. The admin
endpoint gets its own router file, alongside `admin_users.py`.

## Complexity Tracking

There are no constitution violations, so no entries.
