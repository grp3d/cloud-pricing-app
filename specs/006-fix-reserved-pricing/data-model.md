# Data Model: Fix Reserved-Term Pricing Calculation

No entity, field, or schema change — this feature corrects existing calculation logic over
existing data. Documented here only because `SKUSelection.usage_quantity`'s *meaning* is
changing for one case, which downstream tasks need to know.

## `SKUSelection.usage_quantity` (existing field, Postgres — unchanged type/nullability)

- **On-Demand** (`pricing_term = on_demand`): meaning unchanged from `004` — a steady daily
  usage estimate for a no-period unit (e.g., `Hrs`, `Requests`), or the SKU's own quantity
  for a fixed-period unit (e.g., `GB-Mo`).
- **Reserved** (`pricing_term = reserved_1yr` / `reserved_3yr`): **not read by pricing
  calculation at all**, for any purchase option. The frontend no longer offers an input for
  it once a Reserved term is selected (defaulting the submitted value to `"1"` — see
  research.md §4) and it plays no role in `calculate_architecture_price()`'s Reserved
  branch. It does **not** gain a new "number of reserved units" meaning; that concept is
  represented by adding another `SKUSelection` for the same SKU instead (Clarifications,
  FR-008).

## New internal value object (not persisted): `ReservedPrice`

Introduced in `backend/src/pricing_data/pricing.py` alongside `lookup_reserved_price()` —
a plain in-memory result type, not a database table or Pydantic API schema:

- `recurring_rate: float | None` — the `Hrs`-unit recurring hourly rate, or `None` if no
  such row exists in `price_fact` for the given `sku`/term/purchase_option.
- `upfront_fee: float | None` — the `Quantity`-unit one-time upfront fee, or `None` if no
  such row exists (expected/normal for `no_upfront`; a real data gap if missing for
  `partial_upfront`/`all_upfront`, per FR-005).
