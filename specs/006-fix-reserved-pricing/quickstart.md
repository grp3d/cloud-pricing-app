# Quickstart: Fix Reserved-Term Pricing Calculation

Validates: FR-001–FR-008, SC-001–SC-003. Uses the exact SKU from the original bug report,
`2THCJ54S3VW8G6VS` (AmazonEC2 `r7a.48xlarge`, us-east-1), so the fix can be checked against
the same numbers that surfaced it.

## Prerequisites

- Backend and frontend dev servers running per this repo's existing setup — no new
  dependency, no schema/migration to apply.
- Real pricing data available for `2THCJ54S3VW8G6VS` at 1-Year Reserved, all three purchase
  options (confirmed present and, row order, stable across repeated queries as of snapshot
  `2026-09-08` — see Notes on the duplicate-row data quirk this SKU happens to have):

  | Purchase option | Recurring rate (Hrs) | Upfront fee (Quantity) |
  |---|---|---|
  | No Upfront | $12.90693/hr | none |
  | Partial Upfront | $6.66161/hr | $58,356 |
  | All Upfront | $0/hr | $114,946 |

## Scenario 1 — Reserved/No Upfront recurring cost (US1, FR-001, SC-001)

1. Add SKU `2THCJ54S3VW8G6VS` to a Collection with Term "1-Year Reserved", Purchase option
   "No Upfront".
2. Confirm the usage-quantity input is not shown (US3, FR-007).
3. Calculate at "1 month" (31 days).
   - **Expected**: the line item's cost is `$12.90693 × 24 × 31 = $9,602.76` (rounded to
     cents) — **not** `$10.962` (today's bug).
4. Recalculate at "1 day" and "1 year".
   - **Expected**: `$12.90693 × 24 × 1 = $309.77` and `$12.90693 × 24 × 365 =
     $113,064.71` respectively — linear in the duration's day-count only.

## Scenario 2 — Reserved/Partial Upfront includes the upfront share (US2, FR-002, SC-002)

1. Add the same SKU with Term "1-Year Reserved", Purchase option "Partial Upfront".
2. Calculate at "1 month" (31 days).
   - **Expected**: cost = recurring contribution (`$6.66161 × 24 × 31 = $4,956.24`) **plus**
     upfront contribution (`$58,356 × 31 / 365 = $4,956.26`) = **$9,912.50** total — never
     just the recurring portion alone.

## Scenario 3 — Reserved/All Upfront is never $0 (US2, Edge Case)

1. Add the same SKU with Term "1-Year Reserved", Purchase option "All Upfront".
2. Calculate at "1 month".
   - **Expected**: cost = `$0` recurring + `$114,946 × 31 / 365 = $9,762.54` upfront =
     **$9,762.54** total — not `$0`.

## Scenario 4 — No Upfront has no upfront contribution (US2, Edge Case)

1. Reuse Scenario 1's selection (No Upfront).
2. Confirm the total exactly matches Scenario 1's recurring-only figure — no upfront line
   is added, since none applies.

## Scenario 5 — On-Demand is unaffected (US1 AC3, SC-003)

1. Add any On-Demand SKU Selection to the same Architecture.
2. Calculate at any duration before and after this fix is deployed (or compare against a
   pre-fix result recorded earlier).
   - **Expected**: identical result — this fix touches only the Reserved-term code path.

## Notes

- **A pre-existing, out-of-scope data quirk this SKU happens to expose**: `2THCJ54S3VW8G6VS`'s
  Partial-Upfront and All-Upfront `price_fact` rows are each duplicated — two rows per
  `(term, purchase_option, lease_contract_length, unit)` combination with different prices
  and no other distinguishing column (confirmed by selecting every column). This is an
  upstream Parquet data characteristic, not something this fix introduces or is scoped to
  resolve (FR-004 only requires distinguishing the recurring row from the upfront row by
  `unit` — not de-duplicating multiple rows that already share a `unit`). `lookup_reserved_price()`
  takes the first matching row per unit, the same "first-wins" determinism `lookup_price()`
  already relies on elsewhere (established in `004`'s research.md #3) — confirmed stable
  across repeated queries, which is why this quickstart's dollar figures are safe to hardcode
  as regression expectations.
- Scenarios 1–4 double as the real-data integration test in
  `backend/tests/integration/test_duration_pricing.py` (research.md §5) — run it directly
  for a fast, non-UI check: `pytest backend/tests/integration/test_duration_pricing.py -k reserved`.
- If pricing data for this exact SKU/snapshot ever ages out, re-derive the expected dollar
  figures from whatever the current snapshot's `price_fact` rows show for
  `2THCJ54S3VW8G6VS` — the *formulas* in each scenario are the actual thing under test, not
  these specific dollar amounts.
