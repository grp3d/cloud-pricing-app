# Feature Specification: Fix Reserved-Term Pricing Calculation

**Feature Branch**: `006-fix-reserved-pricing`

**Created**: 2026-09-08

**Status**: Draft

**Input**: User description: "Fix incorrect Reserved-term pricing calculation: (1) the current
Reserved proration formula (raw_cost = unit_price × usage_quantity, then × duration_days /
term_days) misinterprets usage_quantity as if it denoted a quantity for the SKU's entire
committed term, when in practice users enter a daily-use estimate (matching the existing UI
hint pattern for other terms) — for example, SKU 2THCJ54S3VW8G6VS priced at 1-Year
Reserved/No Upfront ($12.90693/hr recurring) with usage_quantity=10 (intended as "10 hours of
use per day") currently produces a 30-day estimate of $10.962, when the correct behavior for a
Reserved Instance's recurring hourly charge is that AWS bills for every hour of the commitment
term regardless of actual usage hours per day — so a 31-day slice should cost unit_price × 24
hours × 31 days ≈ $9,602.96 (independent of a "hours used per day" input, since Reserved
recurring cost is not usage-proportional the way On-Demand is). (2) For Reserved selections
with Partial Upfront or All Upfront purchase options, AWS pricing data has two separate price
rows for the same term/purchase_option: a recurring hourly rate row (unit "Hrs") and a
separate one-time lump-sum upfront fee row (unit "Quantity"). The current price lookup
(lookup_price in backend/src/pricing_data/pricing.py) fetches only one row via an unordered
LIMIT 1 with no distinction by unit, and in practice always returns the recurring-rate row —
meaning the upfront fee is silently and completely excluded from every duration-scoped total
for any Partial/All Upfront Reserved selection. The fix must correctly amortize/prorate the
upfront fee's contribution into the duration-scoped total (e.g. the requested duration's share
of the upfront fee, proportional to duration_days/term_days) in addition to the recurring
hourly charge for that same duration, rather than dropping it. Both issues were found by a
user manually verifying a calculated total against the real AWS pricing data for a specific
SKU and term/purchase_option combination."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A Reserved service's recurring cost reflects the full commitment, not a daily-use guess (Priority: P1)

A user who has priced a service as Reserved (1-Year or 3-Year) sees a calculated cost for
that service that reflects what a Reserved commitment actually costs — a recurring charge
for the full requested duration — instead of a number that's been divided down as if it were
scaled by how many hours a day they'd use it.

**Why this priority**: This is the exact defect a user found by hand-checking a real number:
today's total is off by roughly two orders of magnitude for a typical Reserved service,
because the calculation treats a per-day usage estimate as if it were a term-long quantity.
A pricing tool whose core Reserved numbers are wrong at this scale isn't usable for its
primary purpose.

**Independent Test**: Add a Reserved (No Upfront) service to a Collection, calculate at any
duration, and verify the result equals the service's recurring hourly rate × 24 × the
duration's day-count × the selection's quantity — matching what AWS would actually bill for
that commitment over that span.

**Acceptance Scenarios**:

1. **Given** a Collection with one Reserved/No-Upfront SKU Selection, **When** the user
   calculates at "1 month" (31 days), **Then** the displayed cost for that selection equals
   `recurring_hourly_rate × 24 × 31 × quantity` — not a value derived from a "hours per day"
   interpretation of quantity.
2. **Given** the same selection, **When** the user recalculates at "1 day" or "1 year",
   **Then** the displayed cost scales linearly with the requested duration's day-count only
   (1, 31, or 365 days respectively), holding the hourly rate and quantity fixed.
3. **Given** an On-Demand SKU Selection in the same Architecture, **When** the user
   calculates, **Then** its cost is computed exactly as before this fix — On-Demand behavior
   is unchanged.

---

### User Story 2 - An upfront-paid Reserved service's cost includes its upfront share (Priority: P1)

A user who has priced a service as Reserved with Partial Upfront or All Upfront sees a
calculated cost that includes a fair share of the one-time upfront fee for the requested
duration, in addition to any recurring hourly charge — not a total that silently omits the
upfront payment altogether.

**Why this priority**: Silently dropping an entire cost component (the upfront fee) is a
Pricing Data Integrity violation just as serious as User Story 1's miscalculation — a user
choosing All Upfront to minimize recurring cost would currently see an artificially low (or
zero) total with no indication a real, often-large payment is missing.

**Independent Test**: Add a Reserved/Partial-Upfront (or All-Upfront) SKU Selection,
calculate at any duration, and verify the result includes both the recurring-rate
contribution (per User Story 1) and a duration-proportional share of the upfront fee.

**Acceptance Scenarios**:

1. **Given** a Reserved/Partial-Upfront SKU Selection with a known recurring hourly rate and
   a known upfront fee, **When** the user calculates at "1 month" (31 days) with the
   selection's term being 1 year (365 days), **Then** the displayed cost equals the
   recurring-rate contribution (User Story 1) **plus** `upfront_fee × (31 / 365) × quantity`.
2. **Given** a Reserved/All-Upfront SKU Selection (recurring rate of $0/hr), **When** the
   user calculates, **Then** the displayed cost is entirely the duration-proportional share
   of the upfront fee — never $0.
3. **Given** a Reserved/No-Upfront SKU Selection (no upfront fee exists for this option),
   **When** the user calculates, **Then** no upfront contribution is added — the total is
   exactly User Story 1's recurring-rate contribution.

---

### User Story 3 - The quantity field is clearly labeled for a Reserved selection (Priority: P2)

When a user is entering pricing inputs for a Reserved-term selection, the field they'd
otherwise read as a "daily usage estimate" (the label used for On-Demand, time-based-unit
selections) instead clearly indicates it means the quantity of reserved units being
committed to — so a user isn't misled into entering a daily-use number the way the original
bug report's user was.

**Why this priority**: This is the UI-facing root cause of how the User Story 1 bug was
triggered in the first place by a real user; fixing the calculation without also fixing the
misleading label leaves the door open to the same input mistake recurring. Still secondary
to the calculation fixes themselves, which are correctness bugs regardless of labeling.

**Independent Test**: Select a Reserved pricing term for a SKU in the pricing inputs form
and verify the quantity field's guidance text describes "how many of this reservation" —
distinct from the existing "steady daily rate" wording shown for On-Demand, time-based-unit
selections.

**Acceptance Scenarios**:

1. **Given** a user has selected "1-Year Reserved" or "3-Year Reserved" as the pricing term
   for a SKU, **When** they view the usage-quantity input, **Then** its guidance text
   describes the value as the quantity of reserved units, not a daily usage rate.

---

### Edge Cases

- What happens for a Reserved/All-Upfront selection with a $0/hr recurring rate? Its total is
  entirely the amortized upfront share (User Story 2, Acceptance Scenario 2) — never $0.
- What happens if the pricing data is missing the recurring-rate row, the upfront-fee row (for
  Partial/All Upfront), or both, for a Reserved selection? The selection is flagged as
  unpriceable and excluded from the total with a clear reason — never partially calculated
  from whichever row happens to be present, and never guessed (Constitution Principle I).
- What happens with a quantity greater than 1 on a Reserved selection? Both the recurring-rate
  contribution and the upfront-amortized contribution scale by that quantity.
- What happens when the requested duration exceeds the Reserved term's own length (e.g.
  calculating "1 year" for a 1-Year Reserved selection, where duration equals the term
  exactly)? The proportional share is exactly 1× the full recurring/upfront cost for that
  term — no special-casing needed, the existing duration_days/term_days ratio already
  produces this correctly at the boundary.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: For a Reserved-term (1-Year or 3-Year) SKU Selection, the system MUST calculate
  its recurring-rate contribution to a duration-scoped total as: recurring hourly rate × 24 ×
  the requested duration's day-count × the selection's quantity — never scaled by an
  assumption of "hours used per day."
- **FR-002**: For a Reserved-term SKU Selection whose purchase option is Partial Upfront or
  All Upfront, the system MUST add an upfront-amortized contribution to the duration-scoped
  total, equal to: the one-time upfront fee × (requested duration's day-count / the term's
  own day-count) × the selection's quantity.
- **FR-003**: For a Reserved-term SKU Selection whose purchase option is No Upfront, the
  system MUST NOT add any upfront-fee contribution — its total is exactly FR-001's
  recurring-rate contribution.
- **FR-004**: The system MUST retrieve both the recurring rate and, when applicable, the
  upfront fee for a Reserved-term selection as two distinct values from the pricing data —
  never using one in place of the other, and never silently omitting either when both should
  apply.
- **FR-005**: If pricing data is missing a value FR-001/FR-002 needs for a given Reserved
  selection (the recurring rate, or — for Partial/All Upfront — the upfront fee), the system
  MUST flag that selection as unpriceable and exclude it from the total, with a reason
  identifying which value is missing — never proceeding with a partial or guessed
  calculation.
- **FR-006**: On-Demand SKU Selection calculation behavior MUST remain exactly as it is
  today — this fix is scoped to Reserved-term selections only.
- **FR-007**: When a user selects a Reserved pricing term for a SKU, the usage-quantity
  input's guidance text MUST describe the value as the quantity of reserved units being
  committed to, distinctly from the "steady daily rate" guidance shown for On-Demand,
  time-based-unit selections.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a real, currently-available Reserved/No-Upfront SKU, the tool's calculated
  1-month cost matches `recurring_hourly_rate × 24 × 31 × quantity` exactly, verified against
  the underlying AWS pricing data for at least one real SKU.
- **SC-002**: For a real, currently-available Reserved/Partial-Upfront or All-Upfront SKU, the
  tool's calculated total always includes a non-zero upfront-amortized component whenever an
  upfront fee applies to that SKU/term/purchase-option combination.
- **SC-003**: Every On-Demand pricing result produced before this fix is unchanged after it
  (zero regressions in On-Demand calculation behavior).

## Assumptions

- For a Reserved-term SKU Selection, `usage_quantity` (the existing field — no schema change)
  is reinterpreted as the number of identical reserved units (e.g., instances) this selection
  represents, not a usage-duration input. It defaults the same way it already does today (the
  field is unchanged; only its meaning for Reserved terms changes).
- "Hours in the requested duration" uses the same fixed, non-calendar day-counts already
  established in `004-canvas-pricing-improvements` (1 / 31 / 365 days for 1 day / 1 month / 1
  year) — this fix does not change how a duration maps to a day-count, only how a Reserved
  selection's cost is derived from that day-count.
- This fix does not change the On-Demand proration rules from `004` (no-period-unit vs.
  fixed-period-unit classification) — those are out of scope and explicitly required to stay
  unchanged (FR-006).
- No new Postgres schema, DuckDB table, or Parquet data shape is required — this is a
  correction to existing lookup and calculation logic over the same underlying pricing data.
