# Implementation Plan: UI Fixes and Enhancements — Next Iteration

**Branch**: `009-ui-fixes-next-iteration` | **Date**: 2026-09-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-ui-fixes-next-iteration/spec.md`

## Summary

A bug-fix-and-polish pass over 008's five-column workspace, drawn from
`docs/functionality_2026-09-11.md`: three P1 correctness/stability fixes (a specific SKU that
fails to price, Price Change not adjusting for a duration-only change, and a continuation of
008's still-open diagram blank-screen bug — now with a concrete scripted repro); a
Connector/Service data-model correction (refuse a second Service instead of silently replacing
it; render multiple Connectors between the same Collections as distinct edges); pricing-display
formatting (thousand separators, a "Data Timestamp" line replacing a verbose sentence); a
service-search coverage indicator; architecture-diagram styling, an explicit "Add Connector"
dialog, and new size/position persistence; and AWSDataTransfer-specific region-pair filtering
and display. Research (research.md) found this codebase's existing machinery already covers
most of the hard parts — `search_catalog()` already returns a total count, the DB schema already
enforces one-SKU-per-Connector, `fromRegionCode`/`toRegionCode` already flow through the
existing `attributes` dict — so most of this feature is a frontend-presentation and
narrow-backend-behavior pass, not new architecture, with two genuinely new pieces: a
`localStorage`-backed diagram-layout persistence module (research.md corrects a wrong
assumption in spec.md — no such mechanism existed before this feature) and two new optional
DuckDB query filters for AWSDataTransfer's region fields.

## Technical Context

**Language/Version**: TypeScript ~5.6, React 18.3, Vite 5.4 (frontend, unchanged); Python 3.x,
FastAPI ≥0.115, Pydantic ≥2.9 (backend, unchanged) — both `frontend/` and `backend/` are
touched, same split as 008.

**Primary Dependencies**: No new npm/pip dependency. Frontend reuses 008's stack (Tailwind CSS
v4, shadcn/ui, `@xyflow/react`, React Query, `react-router-dom`) plus one new shadcn primitive
copied into `components/ui/` (`Dialog`, for US8 — a source file added via this project's
existing shadcn convention, not a new package; composes on Radix, already an implicit peer of
this codebase's other Radix-based shadcn primitives) and `localStorage` (native) for the new
diagram-layout persistence. Backend reuses FastAPI + Pydantic + DuckDB
(`regexp_matches`/`json_extract_string`, already used identically by every existing catalog
filter) — nothing new to install.

**Storage**: PostgreSQL (existing) — no schema change; one endpoint behavior change only
(`POST /connectors/{id}/sku-selection` refuses instead of replacing on conflict). Parquet-via-
DuckDB (existing) — no schema change; `search_catalog()` gains two optional query parameters.
New `localStorage` key (`cloud-pricing-diagram-layout-{architectureId}`) for diagram layout —
UI/session state per Constitution Principle II, not Postgres-worthy.

**Testing**: Backend — pytest, test-first (Constitution Principle V) for the Connector-conflict
`409` (integration test alongside `test_us2_connectors.py`) and the two new region-code query
filters (unit test alongside `test_catalog_search.py`); US1's investigation itself is exploratory
(see research.md §1) and gets a regression test only once its actual failure point is confirmed
live. Frontend — Vitest + Testing Library, test-first for `decideBaselineUpdate()`'s new
`"duration_only"` branch (extends the existing `priceChange.test.ts`, mirroring 008's
precedent), plus three new pure-logic modules that follow the same test-first `lib/` convention:
`diagramLayout.ts`, `awsDataTransferLabel()`, `edgeOffsetIndex()`. `claude-in-chrome` live
verification against `quickstart.md` for everything presentational (US3's diagram-stability
repro first and foremost — research.md §3 explicitly requires reproducing live before writing a
fix, repeating 008's own stated mistake otherwise — plus US5-US8's UI work and US9's display
integration), per Constitution Principle V's carve-out and 007/008's precedent.

**Target Platform**: Existing web SPA, desktop-width browsers (unchanged from 008).

**Project Type**: Web application (`backend/` + `frontend/` split) — both sides touched.

**Performance Goals**: No new numeric target. `search_catalog()`'s two new optional filters add
at most two more `regexp_matches`/`json_extract_string` clauses to a query shape already proven
performant for the existing three filters over the same ~173k-row-per-region scan; not
benchmarked further per Constitution Principle VI.

**Constraints**: `check-api-types` MUST stay clean for the one endpoint behavior change and the
two new query parameters (Constitution Principle IV; contracts/api.md). FR-002/003's
duration-only Price Change MUST go through the real `calculate-snapshot` recalculation, never a
client-side ratio multiply, even though the ratio is a simple 12× in this app's two-duration
world (Constitution Principle I). US1 and US3 both require a live-verified root cause before a
fix is written (research.md §1/§3) — no speculative fix ships unverified, repeating 008's own
documented mistake with US3 is explicitly out of bounds this time. Existing backend and frontend
test suites stay green throughout.

**Scale/Scope**: Unchanged data scale from 008; bug-fix-and-polish pass, no data-model growth
beyond one new `localStorage` shape.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Pricing Data Integrity**: PASS, with two explicit design obligations tracked, not left
  implicit — (a) FR-002/003's duration-only Price Change MUST come from a real
  `calculate-snapshot` call, never an estimate (research.md §2, data-model.md); (b) US1's SKU
  investigation found a genuine upstream duplicate-row data anomaly (research.md §1) — this plan
  explicitly does NOT introduce a deterministic tie-break or any other silent "pick a price"
  logic beyond the already-existing, already-06-established "first row wins" convention, since
  doing so unprompted would itself risk fabricating a specific-looking-but-arbitrary number;
  any change to that convention is deferred to a live-reproduction finding, not decided
  speculatively now.
- **II. Clear Data-Layer Separation**: PASS — the new diagram-layout persistence
  (`localStorage`, per-browser/per-Architecture) is UI/session state, not user-defined domain
  data, matching 008's column-widths/Prior-Calculation precedent exactly (research.md §7a
  corrects a wrong assumption about an already-existing mechanism, but the *conclusion* —
  localStorage, not Postgres — is unchanged and re-confirmed against the constitution).
- **III. Provider-Extensibility by Design**: PASS — the two new catalog filters
  (`from_region_code`/`to_region_code`) are generic `attributes_json` key filters, not an
  AWSDataTransfer-specific query path (any service's attribute could theoretically be filtered
  the same way); the frontend's AWSDataTransfer label derivation is explicitly service-code-
  gated and additive (FR-030 — every other service's display is untouched), not a new
  provider-wide assumption.
- **IV. Type-Safe Frontend/Backend Contract**: GATE — the one endpoint behavior change and the
  two new query parameters are both Pydantic/FastAPI-native (contracts/api.md); `check-api-types`
  MUST pass after the `search_skus` signature change generates updated TypeScript types.
- **V. Test-First Development**: GATE — the Connector-conflict `409` (backend, pricing/data-
  relationship logic) and the two new region-code DuckDB filters (backend, catalog-query logic)
  are NON-NEGOTIABLE test-first; `decideBaselineUpdate()`'s new branch (frontend, real
  extractable pricing-comparison logic, 007/008 `serviceConfigSelection.ts`/`priceChange.ts`
  precedent) is also test-first. Everything else is presentational UI work under Principle V's
  carve-out (tests-after / live-verified) — except US1 and US3, which are correctness bugs but
  are *investigative* before they're fixable (research.md §1/§3 both found the obvious
  candidate logic does NOT reproduce the failure in isolation), so their test-first obligation
  attaches once the live investigation identifies the actual faulty code, not to a guess now.
- **VI. Simplicity & YAGNI**: PASS, with explicit scope fences carried from research.md: no
  deterministic-tie-break redesign for US1's duplicate-row finding ahead of confirming that's
  even the actual bug; no Postgres-backed diagram-layout table; no new npm dependency for a
  Dialog component already coverable by this project's existing shadcn-copy-in convention; no
  generic multi-provider attribute-filter framework beyond the two named parameters FR-029 asks
  for.

No unjustified violations. Complexity Tracking is not needed.

**Post-Design re-check** (after Phase 0/1 artifacts above): every gate still holds against the
concrete design. I's two obligations are both discharged by name in research.md §1/§2 and
data-model.md's `BaselineDecision`/`"duration_only"` section; II is confirmed by data-model.md's
`DiagramLayout` section (localStorage-only, explicitly not a new Postgres table, with the
corrected-assumption note carried into spec.md's own Assumptions section so the record stays
accurate); III is confirmed by contracts/api.md's generic (not AWSDataTransfer-named)
`from_region_code`/`to_region_code` parameters; IV's gate is discharged by contracts/api.md's
explicit before/after schemas for both backend changes. No new violations were introduced while
designing data-model.md/contracts/quickstart.md.

## Project Structure

### Documentation (this feature)

```text
specs/009-ui-fixes-next-iteration/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   └── api.md
├── checklists/
│   └── requirements.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── api/
│   │   └── connectors.py          # FR-008: attach_connector_sku — 409 instead of replace
│   ├── pricing_data/
│   │   └── catalog.py             # FR-029: search_catalog() — two new optional filters
│   └── models/
│       └── schemas.py             # no schema change (contracts/api.md — behavior-only + query params)
└── tests/
    ├── unit/
    │   └── test_catalog_search.py       # extended: from_region_code/to_region_code cases
    └── integration/
        └── test_us2_connectors.py       # extended (or sibling file): 409-on-conflict case

frontend/
├── src/
│   ├── pages/
│   │   └── WorkspacePage.tsx             # US2: "duration_only" handling; US8: Add Connector
│   │                                      #   dialog wiring; US3 fix once live-confirmed
│   ├── components/
│   │   ├── CatalogSearchPanel.tsx        # US5: reworded/repositioned/styled indicator;
│   │   │                                  #   US9: From/To region fields + label integration
│   │   └── ui/
│   │       └── dialog.tsx                # NEW — shadcn Dialog primitive (US8)
│   ├── components/workspace/
│   │   ├── ArchitectureDiagramPanel.tsx  # US3 fix (once confirmed); US4 edge offset; US7
│   │   │                                  #   styling/resize-handle/persistence/underline;
│   │   │                                  #   US8 Add Connector button + dialog; US9 labels
│   │   └── PricingPanel.tsx              # US6: thousand separators, Data Timestamp line;
│   │                                      #   US9: per-SKU label
│   ├── lib/
│   │   ├── priceChange.ts                # US2: new "duration_only" BaselineDecision branch
│   │   ├── diagramLayout.ts              # NEW — US7: localStorage size/position persistence
│   │   ├── awsDataTransfer.ts            # NEW — US9: derived region-pair label
│   │   └── edgeOffset.ts                 # NEW — US4: parallel-Connector offset index
│   └── api/client.ts                     # US9: from_region_code/to_region_code search params
└── tests/unit/
    ├── priceChange.test.ts               # extended: "duration_only" case (test-first)
    ├── diagramLayout.test.ts             # new (test-first)
    ├── awsDataTransfer.test.ts           # new (test-first)
    └── edgeOffset.test.ts                # new (test-first)
```

**Structure Decision**: Existing `backend/` + `frontend/` split (unchanged from 001-008). No new
top-level directories. New frontend logic stays in `frontend/src/lib/` as small, pure,
independently-testable modules — the same 007/008 convention (`serviceConfigSelection.ts`,
`columnWidths.ts`, `priceChange.ts`) — rather than growing the already-large
`ArchitectureDiagramPanel.tsx`/`WorkspacePage.tsx` components with inline logic. The one new UI
primitive (`components/ui/dialog.tsx`) follows this project's existing shadcn-copy-in convention
exactly, alongside `select.tsx`, `button.tsx`, etc.

## Complexity Tracking

*No Constitution Check violations requiring justification.*
