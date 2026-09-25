# Implementation Plan: Canvas Service Icons & Per-Architecture Pricing Results

**Branch**: `015-canvas-service-icons` | **Date**: 2026-09-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/015-canvas-service-icons/spec.md`

## Summary

This feature makes three changes:

- **Canvas icons (US1–US3).** Each service row in the architecture canvas becomes an official
  AWS architecture icon. A hover or focus pop-up shows the reformatted details: service code,
  `Sku:`, summary, `UsageType:` and `Operation:`. Icons scale with canvas zoom.
- **Per-architecture pricing (US4).** Column 5 shows the active architecture's own last result.
  Results are persisted per architecture in the browser, auto-calculated when absent, and marked
  out of date when the architecture's priced contents change.
- **Word-wrap toggle (US5).** The Price per Sku toggle moves to that section's heading row.

**Technical approach**: A checked-in, script-generated service-code / product-family → icon map,
with only the referenced SVGs copied into `frontend/src/assets/aws-icons/`. The backend adds one
read-only response field, `SKUSelectionOut.product_family`, resolved from Parquet in the existing
batched attributes lookup. The pop-up reuses the existing Radix tooltip with zoom-proportional
font sizing. Pricing results use the established `localStorage` + type-guard pattern
(`priorCalculation.ts`). The calculate mutation captures its request context in mutation
variables, so late results can't land on the wrong architecture. Details are in
[research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.6 / React 18 (frontend)

**Primary Dependencies**: FastAPI, Pydantic, DuckDB (backend); Vite 5, @xyflow/react 12,
radix-ui (shadcn Tooltip), TanStack Query 5, Tailwind 4 (frontend). **No new dependencies.**

**Storage**: Parquet via DuckDB (read-only, adds `product_family` to the existing lookup);
browser `localStorage` for per-architecture pricing results. **No Postgres changes or
migrations.**

**Testing**: pytest (backend unit and contract), Vitest + Testing Library (frontend unit and
component), `npm run check-api-types` for contract drift

**Target Platform**: Modern desktop browsers; local FastAPI server

**Project Type**: Web application (`backend/` + `frontend/`)

**Performance Goals**: A stored result renders in under 1 s after switching, with no network
request (SC-006). Adding icons adds no extra DuckDB queries per architecture load: still one
attributes lookup per distinct region.

**Constraints**: Icons stay crisp at every zoom level (SVG). Shipped icon assets are no more than
about 1 MB total and loaded on demand. The icon package and Parquet directory are **build-time
developer inputs only**, not runtime or CI dependencies.

**Scale/Scope**: 250 AWS service codes in the current snapshot (≥90% mapped to a non-fallback
icon); about 180 SVG assets; architectures with up to tens of services per box.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Status |
|---|---|---|
| I. Pricing Data Integrity | No price is computed, estimated or edited client-side. Stored results are verbatim `calculate` responses, including `snapshot_date`, which is still shown as Data Timestamp for traceability. Stale results are **explicitly flagged** (FR-018a), not silently shown as current. | ✅ Pass |
| II. Clear Data-Layer Separation | `product_family` is read from Parquet at response time and never written to Postgres. Derived pricing results live in browser storage only; FR-015 forbids writing them to the application database. | ✅ Pass |
| III. Provider-Extensibility | The icon resolver and generated map are AWS-namespaced (`awsServiceIcons*`), like the existing `awsDataTransfer.ts`. The icon component takes a resolved icon, so another provider adds a sibling resolver rather than rewriting. `product_family` is a provider-neutral concept on a provider-neutral schema. No AWS assumption is added to shared tables or endpoints. | ✅ Pass |
| IV. Type-Safe Contract | The new field is declared on the Pydantic `SKUSelectionOut`, `schema.d.ts` is regenerated, and `check-api-types` gates drift. The stored result is typed with the generated `CalculationResult` type. | ✅ Pass |
| V. Test-First | DuckDB query change (`resolve_product_details`) and contract tests are written first. Pure logic that transforms a price or user-defined relationship (pricing-result store, priced-contents equality, auto-calculate decision, request-context capture) is test-first. The icon resolver and pop-up line builder are also test-first; they are cheap and pin FR-003/FR-008. Pure presentational layout (icon row, heading row) may be tests-after. | ✅ Pass |
| VI. Simplicity & YAGNI | No new datastore, dependency, endpoint or abstraction layer. It reuses Tooltip, `localStorage` helpers, `summarizeAttributes`, `awsDataTransferLabel` and the price-change comparison. The mapping is static data, not a runtime matching engine. | ✅ Pass |

**Post-Phase-1 re-check**: The design artifacts (data-model.md, contracts/) introduce nothing
beyond the table above. The one documented deviation from the spec's original assumption, using a
General resource icon for AWSDataTransfer, has been written back into the spec's Assumptions.
**Gate: PASS. No Complexity Tracking entries.**

## Project Structure

### Documentation (this feature)

```text
specs/015-canvas-service-icons/
├── plan.md              # This file
├── research.md          # Phase 0: icon matching, product_family, zoom, storage, races
├── data-model.md        # Phase 1: API field, icon map, pop-up lines, result entry + lifecycle
├── quickstart.md        # Phase 1: end-to-end validation guide
├── contracts/
│   ├── api.md           # SKUSelectionOut.product_family (additive)
│   └── ui.md            # Canvas icon, pop-up, pricing column layout/states
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
backend/
├── scripts/
│   └── generate_aws_service_icon_map.py        # NEW: approximate matching + overrides → TS map + SVG copies + report
├── src/
│   ├── models/schemas.py                       # SKUSelectionOut.product_family
│   ├── pricing_data/catalog.py                 # resolve_product_details(); resolve_attributes → wrapper
│   └── services/architecture_service.py        # batch + single paths attach product_family
└── tests/
    ├── unit/                                   # resolve_product_details (fixture Parquet)
    ├── contract/test_architectures.py          # product_family on detail
    ├── contract/test_sku_selections.py         # product_family on create/update
    └── fixtures/pricing_parquet/               # ensure product_family values present (via build_test_pricing_fixture.py)

frontend/
├── src/
│   ├── assets/aws-icons/*.svg                  # NEW (generated): referenced service icons + fallback + data-stream
│   ├── lib/
│   │   ├── awsServiceIcons.generated.ts        # NEW (generated): code→icon, (code,family)→icon
│   │   ├── awsServiceIcons.ts                  # NEW: resolveAwsServiceIcon()
│   │   ├── servicePopup.ts                     # NEW: buildServicePopupLines()
│   │   ├── architecturePricingResults.ts       # NEW: read/write/remove result entry (localStorage)
│   │   └── priceChange.ts                      # + PricedContentsEntry, pricedContentsEqual()
│   ├── components/workspace/
│   │   ├── ArchitectureDiagramPanel.tsx        # ServiceList → ServiceIcon row + zoom-scaled Tooltip
│   │   └── PricingPanel.tsx                    # heading-row wrap toggle; out-of-date notice
│   ├── pages/WorkspacePage.tsx                 # per-architecture result/error maps, auto-calc, duration sync, delete cleanup
│   └── api/generated/schema.d.ts               # regenerated
└── tests/unit/
    ├── awsServiceIcons.test.ts
    ├── servicePopup.test.ts
    ├── architecturePricingResults.test.ts
    ├── priceChange.test.ts                     # + pricedContentsEqual cases
    ├── ServiceIconList.test.tsx
    └── PricingPanel.test.tsx
```

**Structure Decision**: This uses the existing web-application layout (`backend/` + `frontend/`).
The new pure logic goes in `frontend/src/lib/`, following the existing one-concern-per-module
convention (`awsDataTransfer.ts`, `priorCalculation.ts`). The generator script sits beside the
existing data-prep scripts in `backend/scripts/`, which already have DuckDB and the Parquet path
configuration.

## Complexity Tracking

No constitution violations, so no entries.
