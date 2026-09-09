# Research: Fix Reserved-Term Pricing Calculation

## 1. Distinguishing the recurring rate from the upfront fee (FR-002, FR-004, FR-005)

**Decision**: Add a new, Reserved-specific lookup, `lookup_reserved_price()`, in
`backend/src/pricing_data/pricing.py`. It queries `price_fact` for every row matching
`sku`/`term='Reserved'`/`lease_contract_length`/`purchase_option` (no `LIMIT 1`), then in
Python splits the (at most two) rows by their `unit` column: `unit == 'Hrs'` is the recurring
rate, `unit == 'Quantity'` is the one-time upfront fee. Returns a small
`ReservedPrice(recurring_rate: float | None, upfront_fee: float | None)`.

**Rationale**: Confirmed against the real snapshot (via direct DuckDB query during
diagnosis) that a Reserved/Partial-Upfront or All-Upfront combination always has exactly
two `price_fact` rows sharing every other column, distinguished only by `unit`; a
Reserved/No-Upfront combination has exactly one (`Hrs`, since there's no upfront fee to
have a `Quantity` row for). `lookup_price()`'s existing unordered `LIMIT 1` — with no `unit`
filter — is exactly the bug: it deterministically returns whichever row the parquet scan
happens to read first (confirmed always the `Hrs` row in practice), silently discarding the
`Quantity`/upfront row every time. Filtering by `unit` explicitly, rather than relying on
row order, removes the ambiguity entirely.

**Alternatives considered**:
- Add an `ORDER BY` to `lookup_price()`'s existing query and keep `LIMIT 1`: rejected — this
  would still only ever return ONE of the two rows a Partial/All-Upfront selection needs
  both of; the bug isn't which row wins an arbitrary priority order, it's that both rows are
  needed simultaneously.
- Reuse `lookup_price()` twice (once "pretending" a `unit` param existed) by adding a `unit`
  filter parameter to it: rejected — `lookup_price()` is also the On-Demand path (a single,
  unambiguous row), and On-Demand callers never need to specify a `unit` to disambiguate;
  overloading it with an optional, Reserved-only parameter is more confusing than a small,
  purpose-named sibling function that only Reserved selections call.

## 2. The Reserved cost formula itself (FR-001, FR-002, FR-003)

**Decision**: Restructure `calculate_architecture_price()` to branch on `term_days is not
None` (Reserved) *before* doing any pricing lookup, rather than computing a shared
`unit_price` first and only branching for proration afterward (today's structure). The
Reserved branch:

```
recurring_contribution = recurring_rate * 24 * duration_days
upfront_contribution   = 0                                        (No Upfront), or
                          upfront_fee * duration_days / term_days  (Partial/All Upfront)
displayed_cost = recurring_contribution + upfront_contribution
```

`usage_quantity` is not read anywhere in this branch (Clarifications — the field has no
Reserved-term meaning and none is added). The On-Demand branch (`classify_unit`-driven
proration, using `resolve_units`/`lookup_price` exactly as today) is untouched.

**Rationale**: This directly implements the spec's FR-001/002/003 formulas. Restructuring
the branch point earlier (before any lookup) avoids awkwardly retrofitting the new
two-value `ReservedPrice` result into a code path shaped around a single `unit_price`
scalar, and makes the Reserved and On-Demand paths read as two clearly separate,
independently-testable procedures — matching how distinctly they're now specified.

**Alternatives considered**:
- Keep computing `raw_cost = unit_price * usage_quantity` for Reserved and multiply by
  `duration_days / term_days`: this is exactly today's bug (raw_cost silently treats
  `usage_quantity` as a term-long quantity); rejected outright, it's the defect being fixed.

## 3. No new "reservation quantity" field (Clarifications, FR-008, Constitution VI)

**Decision**: No schema, model, or API change to represent "more than one reserved unit."
An Architecture needing several identical reserved instances gets several SKU Selections
for that SKU (already fully supported — nothing in the data model or API enforces
uniqueness of `(collection, sku)`).

**Rationale**: This was the explicit, reasoned answer settled during `/speckit-clarify` —
mathematically a linear quantity multiplier is valid AWS pricing behavior, but this app
already has an equivalent, simpler mechanism (multiple selections), so adding a second one
is unjustified complexity (Principle VI).

## 4. Hiding, not relabeling, the usage-quantity input for a Reserved term (FR-007)

**Decision**: In `PricingInputsForm.tsx`, the usage-quantity `<label>`/`<input>` and its
hint paragraph render **only** when `term === "on_demand"`. When the user switches `term`
to `reserved_1yr`/`reserved_3yr`, the component also resets its internal `quantity` state to
`"1"` — a harmless, self-consistent value for the still-required API field to carry (see
below), even though Reserved pricing never reads it.

`usageQuantityHint()` (`frontend/src/lib/usageQuantityHint.ts`) drops its `term` parameter
entirely — its `term !== "on_demand" → "period_denominated"` branch is now unreachable (the
only call site never invokes it for a Reserved term), so keeping the parameter would be
dead weight. It becomes a pure function of `unit` alone: `no_period → "per_day_estimate"`,
`fixed_period → "period_denominated"` (still correctly used for an On-Demand fixed-period
unit like `GB-Mo`), else `null`.

**Rationale**: Directly implements FR-007 ("hide or disable... rather than showing it with
guidance that no longer applies") and removes the exact UI element that misled the
bug-reporting user into entering a "hours per day" value in the first place. Dropping the
unused `term` parameter from `usageQuantityHint` is a small, justified simplification
(Principle VI) now that its Reserved-term branch can never be reached.

**Why the underlying field still needs *some* submitted value**: `usage_quantity` remains a
required field on the `SKUSelectionCreate`/`Update` API contract (no schema change, per
Assumptions) — hiding its input in the UI doesn't remove the field from the request payload.
Defaulting it to `"1"` when a Reserved term is selected keeps the stored value meaningful
("one of this reservation," consistent with how a user would read it if they ever inspected
raw data) rather than leaving it at whatever arbitrary number was last typed for an
On-Demand selection, even though the Reserved pricing math never reads it either way.

## 5. Testing approach (Constitution Principle V)

**Decision**: Full test-first discipline, matching `004`'s precedent for pricing-calculation
logic:
- `backend/tests/unit/test_pricing_units.py` (or a focused new test module) gets
  test-first coverage for `lookup_reserved_price()`: returns both values when both rows
  exist, `upfront_fee=None` when only the `Hrs` row exists (No Upfront), and `None`
  outright when no row matches.
- `backend/tests/unit/test_price_calculation.py` gets test-first coverage for the
  restructured Reserved branch: recurring-only total (No Upfront), recurring+amortized-
  upfront total (Partial Upfront), upfront-only total when recurring is `$0` (All Upfront),
  unpriceable-with-reason for a missing recurring or upfront row, and an On-Demand
  regression check (byte-for-byte unchanged result) per SC-003.
- `backend/tests/integration/test_duration_pricing.py` gets a real-data integration test
  using the exact SKU from the bug report, `2THCJ54S3VW8G6VS` (1-Year Reserved/No Upfront),
  asserting the corrected ~$9,602.96-order total for a 1-month duration — the same
  real-snapshot testing discipline `004` established (no mocks for this class of test).
- Frontend: `frontend/tests/unit/usageQuantityHint.test.ts` updated for the simplified
  (unit-only) signature; `frontend/tests/unit/PricingInputsForm.test.tsx` gets a new test
  that the usage-quantity input is absent (not merely visually hidden — actually absent
  from the rendered form) once a Reserved term is selected.
