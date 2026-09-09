# Implementation Plan: Fix Reserved-Term Pricing Calculation

**Branch**: `006-fix-reserved-pricing` | **Date**: 2026-09-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-fix-reserved-pricing/spec.md`

## Summary

Two Pricing Data Integrity bugs in Reserved-term calculation, both found by a user
hand-checking a real number against real AWS pricing data: (1) the Reserved proration
formula silently misinterprets `usage_quantity` as a term-long quantity instead of a "hours
per day" estimate, producing a total off by roughly two orders of magnitude — fixed by
computing a Reserved selection's recurring contribution as `recurring_rate × 24 ×
duration_days`, never scaled by `usage_quantity` at all (Clarifications: the field has no
Reserved-term meaning, and none is added — multiple reserved units means multiple SKU
Selections). (2) `lookup_price()`'s ambiguous, unordered `LIMIT 1` always returns the
recurring-rate row for a Partial/All-Upfront Reserved selection, silently dropping the
upfront fee from every total — fixed by a new `lookup_reserved_price()` that fetches both
rows explicitly (by `unit`) and amortizes the upfront fee proportionally into the
duration-scoped total. See `research.md` for full rationale and rejected alternatives.

## Technical Context

**Language/Version**: Python 3.11 (backend: `pricing_data/pricing.py`,
`services/price_calculation.py`); TypeScript ~5.6 / React 18.3 (frontend:
`PricingInputsForm.tsx`, `usageQuantityHint.ts`).

**Primary Dependencies**: `duckdb` (already in use, read-only `price_fact` query), Python
`decimal.Decimal` for exact money math (existing pattern from `004`). No new dependency,
frontend or backend.

**Storage**: DuckDB over the existing read-only `price_fact` Parquet table — no new table,
column, or Parquet shape; only the query/lookup logic over it changes (research.md §1).

**Testing**: pytest, test-first (Constitution Principle V is non-negotiable for pricing
calculation logic) — unit tests for the new lookup and the restructured calculation branch,
plus a real-data integration test using the exact bug-report SKU
(`2THCJ54S3VW8G6VS`, research.md §5). Vitest for the two frontend changes.

**Target Platform**: Existing web app (React SPA + FastAPI backend) — no new platform.

**Project Type**: Web application (existing `backend/` + `frontend/` split); this feature
touches both, but only within already-established files.

**Performance Goals**: Negligible — at most one extra `price_fact` row read per Reserved
selection (the upfront row, when present), still one query per calculation as today.

**Constraints**: No Postgres schema, DuckDB table, or Parquet shape change (Assumptions);
On-Demand calculation results MUST be byte-for-byte unchanged (FR-006, SC-003); no new
"reservation quantity" field or setting (FR-008, Clarifications).

**Scale/Scope**: Unchanged — same expected number of SKU Selections per Architecture.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applicability | Assessment |
|---|---|---|
| I. Pricing Data Integrity | Central | This fix exists *because of* two violations of this principle (a silently wrong Reserved total; a silently dropped upfront fee) — the entire feature is bringing Reserved-term calculation back into compliance with "never fabricate/guess, always traceable." |
| II. Clear Data-Layer Separation | Applies, unaffected | Still read-only DuckDB/Parquet for pricing, no Postgres schema touched; the vendor-data/user-data boundary doesn't move. |
| III. Provider-Extensibility by Design | Applies, unaffected | No new AWS-specific hardcoding beyond what `_TERM_MAP`/`_PURCHASE_OPTION_MAP` (existing, from `004`) already encode; the new lookup follows the same pattern. |
| IV. Type-Safe Frontend/Backend Contract | Applies, unaffected | No API request/response shape changes — `SKUSelectionCreate`/`Update` and `CalculationResult` schemas are untouched; nothing for `check-api-types` to drift on. |
| V. Test-First Development | Non-negotiable, applies fully | This *is* pricing calculation logic — every behavior change (the new lookup, the restructured Reserved branch) gets a failing test written first, per research.md §5. |
| VI. Simplicity & YAGNI | Applies | The Clarifications decision (no new quantity field; reuse multi-selection) is a direct application of this principle — the simpler, already-existing mechanism covers the same need. |

**Gate result**: PASS. No violations; Complexity Tracking table not needed.

## Project Structure

### Documentation (this feature)

```text
specs/006-fix-reserved-pricing/
├── plan.md              # This file (/speckit-plan command output)
├── research.md           # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command) — no entity changes
├── quickstart.md         # Phase 1 output (/speckit-plan command)
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

No `contracts/` — no API request/response shape changes (see Constitution Check, Principle
IV).

### Source Code (repository root)

```text
backend/
├── src/
│   ├── pricing_data/
│   │   └── pricing.py                 # NEW: lookup_reserved_price() + ReservedPrice
│   └── services/
│       └── price_calculation.py       # Reserved branch restructured (research.md §2)
└── tests/
    ├── unit/
    │   ├── test_pricing_units.py      # extended: lookup_reserved_price() coverage
    │   └── test_price_calculation.py  # extended: Reserved formula + unpriceable cases
    └── integration/
        └── test_duration_pricing.py   # extended: real SKU 2THCJ54S3VW8G6VS scenarios

frontend/
├── src/
│   ├── components/
│   │   └── PricingInputsForm.tsx      # usage-quantity input hidden for Reserved terms
│   └── lib/
│       └── usageQuantityHint.ts       # simplified: drops the now-dead `term` parameter
└── tests/
    └── unit/
        ├── usageQuantityHint.test.ts      # updated for the simplified signature
        └── PricingInputsForm.test.tsx     # extended: input absent for a Reserved term
```

**Structure Decision**: Web application structure (established `001`-`005`) is unchanged.
This feature is scoped to the pricing-calculation layer of `backend/` and the pricing-input
form of `frontend/` — no new directory, no new top-level module.

## Complexity Tracking

*No violations — table not needed.*
