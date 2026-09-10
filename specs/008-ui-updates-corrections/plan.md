# Implementation Plan: UI Updates and Corrections

**Branch**: `008-ui-updates-corrections` | **Date**: 2026-09-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-ui-updates-corrections/spec.md`

## Summary

A broad correction-and-enhancement pass over 007's five-column workspace: fix the
diagram's resize/auto-fit/VPC-click bugs and let its panel use much more vertical height
(US1); stop column 3 from collapsing to zero width and extend collapsibility to columns
1-3 (US2); clearer column/section headers and provider layout (US3); draggable,
per-browser-persisted column widths (US4); rounded, comparison-aware pricing display —
Price Change with duration-adjusted, edit-triggered baselines, and a per-SKU cost
breakdown (US5); a smaller, sky-colored visual theme (US6); and a more capable service
search — regex matching, a fixed-in-view filter row, a 200-result cap, a true match-count
indicator, and alphabetical sort by displayed text (US7). Unlike 007, this feature touches
`backend/` as well as `frontend/`: the search-count indicator (FR-024) and regex matching
(FR-020) need catalog-query changes, and Price Change's duration-adjustment (FR-016a) needs
a new, ownership-free "price this set of selections" calculation endpoint — see research.md.

## Technical Context

**Language/Version**: TypeScript ~5.6, React 18.3, Vite 5.4 (frontend, unchanged); Python
3.x, FastAPI ≥0.115, Pydantic ≥2.9 (backend, unchanged) — both `frontend/` and `backend/`
are touched by this feature, unlike 007.

**Primary Dependencies**: No new dependencies anticipated. Frontend reuses 007's stack
(Tailwind CSS v4, shadcn/ui, `lucide-react`, React Query, `@xyflow/react`,
`react-router-dom`) plus `localStorage` (native, no library) for column widths and the
Prior Calculation snapshot. Backend reuses FastAPI + Pydantic + DuckDB (`duckdb>=1.1`,
whose `regexp_matches(string, pattern, options)` — RE2 syntax — covers FR-020's regex
matching, research.md §2) + SQLAlchemy (`Architecture` ORM shape, reused transiently for
FR-016a, research.md §5) — nothing new to install.

**Storage**: PostgreSQL (existing, user data) — unaffected in shape; no new tables (Prior
Calculation and column widths are frontend-only, `localStorage`-persisted, per
Clarifications — not written to Postgres, Constitution Principle II: they are UI/session
preferences, not user-defined domain data). Parquet-via-DuckDB (existing, vendor pricing) —
queried differently (regex instead of exact/`ILIKE`, plus a count) but not written to.

**Testing**: Backend — pytest, test-first (Constitution Principle V) for every touched
DuckDB query change (FR-020/023/024's `search_catalog`) and the new snapshot-calculation
endpoint (FR-016a), since both are pricing/catalog-query logic. Frontend — Vitest +
Testing Library, test-first for the one genuinely new piece of extractable pure logic (the
"did the architecture change" / baseline-update decision behind FR-016/016a, mirroring
007's `ServiceConfigSelection` precedent, research.md §6); `claude-in-chrome` live
verification against `quickstart.md` for everything presentational (layout, collapse,
resize, labels, color, search UX), per Constitution Principle V's carve-out and 005/007's
precedent.

**Target Platform**: Existing web SPA, desktop-width browsers (unchanged from 007).

**Project Type**: Web application (`backend/` + `frontend/` split) — both sides touched.

**Performance Goals**: No new numeric target. The one new query cost is FR-024's total-count
query (an additional `COUNT(*)` alongside the existing paged `SELECT`, same `WHERE` clause,
over the same ~173k-row-per-region Parquet scan the existing search already performs) —
expected to stay well within the search's existing interactive feel; not benchmarked
further per Constitution Principle VI (no speculative performance work ahead of a real
problem).

**Constraints**: `check-api-types` MUST stay clean for every new/changed API surface
(Constitution Principle IV) — the count field and the new snapshot-calculation endpoint
both need Pydantic schemas that generate matching TypeScript types. FR-016a's duration
adjustment MUST go through the same authoritative calculation path as any other price
(Constitution Principle I) — never a mathematical estimate. Existing backend test suite
and existing frontend tests stay green throughout.

**Scale/Scope**: Unchanged data scale from 007; this is a UI-correction and
search/pricing-display enhancement pass, not a data-model change.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Pricing Data Integrity**: PASS, with one explicit design obligation — FR-016a's
  duration-adjusted comparison total MUST come from a real calculation call (the same
  pricing lookups every other price uses), never a scaled/estimated number. Tracked as a
  research.md decision (§5) and a data-model.md/contracts requirement, not left implicit.
- **II. Clear Data-Layer Separation**: PASS — column widths and the Prior Calculation
  snapshot are `localStorage`-only UI/session state (Clarifications), not written to
  Postgres; they are not user-defined domain data (collections, linking tables) and must
  not be modeled as if they were.
- **III. Provider-Extensibility by Design**: PASS — FR-008's provider icons key off the
  provider dimension 007 already modeled (no new AWS-only assumption); the new
  snapshot-calculation endpoint (FR-016a) is a generic "price this set of selections"
  capability, not AWS-specific.
- **IV. Type-Safe Frontend/Backend Contract**: GATE — every backend surface change
  (`CatalogSearchResult`'s new total-count field, the new snapshot-calculation endpoint's
  request/response schemas) MUST have Pydantic models generating the TypeScript types
  `check-api-types` checks; this plan's contracts/ output defines those schemas explicitly
  before implementation starts.
- **V. Test-First Development**: GATE — the touched `search_catalog` DuckDB query logic
  (regex + count) and the new snapshot-calculation endpoint are pricing/catalog-query logic
  and are NON-NEGOTIABLE test-first per Principle V; tasks.md must sequence their tests
  before their implementation. Everything else in this feature is presentational UI work
  under Principle V's carve-out (tests-after / live-verified), matching 007's precedent —
  except the frontend's baseline-update decision logic (FR-016/016a), which is real
  extractable logic and gets test-first unit tests on the same precedent as
  `ServiceConfigSelection` (007).
- **VI. Simplicity & YAGNI**: PASS, with explicit scope fences carried from the spec: no
  pagination UI beyond the count indicator (FR-024 explicitly defers it); no generic
  multi-provider icon-resolution system beyond the three files FR-008 names; no new
  settings/preferences framework for column widths beyond a `localStorage` key (FR-013).

No unjustified violations. Complexity Tracking is not needed.

**Post-Design re-check** (after Phase 0/1 artifacts below): every gate above still holds
against the concrete design. Notably: I's obligation is discharged by research.md §5's
`calculate-snapshot` endpoint reusing `calculate_architecture_price()` verbatim against a
transient (never-persisted) object graph — no estimation anywhere; II is confirmed by
data-model.md — nothing new is written to Postgres, both new stateful concepts are
`localStorage`-only; IV's gate is discharged by contracts/api.md's explicit Pydantic-shaped
request/response definitions for both the extended `CatalogSearchResult` and the new
endpoint. No new violations were introduced while designing data-model.md/contracts/
quickstart.md.

## Project Structure

### Documentation (this feature)

```text
specs/008-ui-updates-corrections/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── api/
│   │   ├── catalog.py            # FR-020/023/024: regex + count in GET /catalog/skus
│   │   └── calculate.py          # FR-016a: new snapshot-calculation endpoint alongside it
│   ├── pricing_data/
│   │   └── catalog.py            # FR-020/024: search_catalog() regex WHERE + COUNT query
│   ├── services/
│   │   └── price_calculation.py  # FR-016a: reused, unchanged, against a transient snapshot
│   └── models/
│       └── schemas.py            # FR-024: CatalogSearchResult.total; FR-016a: new request/
│                                  #   response models
└── tests/
    ├── unit/                     # search_catalog regex/count tests; snapshot-calc tests
    └── integration/              # new endpoint's contract-level test

frontend/
├── src/
│   ├── pages/
│   │   └── WorkspacePage.tsx           # US2/US4: column 3 always-present, column-width
│   │                                    #   drag state, Prior Calculation orchestration
│   ├── components/workspace/
│   │   ├── ProviderArchitecturePanel.tsx  # US3: layout, "(soon)" removal, provider icons
│   │   ├── CollectionsPanel.tsx           # US2/US3: collapse icon, header/section rename,
│   │   │                                   #   separators
│   │   ├── ServiceConfigPanel.tsx         # US2/US3: always-present + "Service Editor" header
│   │   ├── ArchitectureDiagramPanel.tsx   # US1: resize/auto-fit/VPC-click-crash fixes (or
│   │   │                                   #   replacement, per research.md §1)
│   │   └── PricingPanel.tsx               # US5: rounding, Price Change + arrow, Price per Sku
│   ├── components/
│   │   └── CatalogSearchPanel.tsx    # US7: regex fields, sticky filters, 200 cap, count,
│   │                                  #   sort
│   ├── lib/
│   │   ├── columnWidths.ts           # US4: new — localStorage read/write for widths
│   │   └── priceChange.ts            # US5: new — baseline-update decision (test-first)
│   └── index.css                     # US6: font-size step, sky color tokens
└── tests/unit/
    ├── priceChange.test.ts           # new, test-first
    └── columnWidths.test.ts          # new (pure localStorage-adjacent logic, low risk)
```

**Structure Decision**: Existing `backend/` + `frontend/` split (unchanged from 001-007).
No new top-level directories. New frontend modules are pure-logic files under
`frontend/src/lib/`, matching 007's `serviceConfigSelection.ts` precedent, so the one
genuinely new piece of testable logic per area (price-change baseline decisions; column-
width persistence) stays cleanly separated from the presentational components that consume
it.

## Complexity Tracking

*No Constitution Check violations requiring justification.*
