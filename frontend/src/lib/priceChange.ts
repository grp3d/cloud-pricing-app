/**
 * The Price Change baseline-update decision (US5, FR-015/016/016a, research.md §6) —
 * extracted as pure, test-first logic (Constitution Principle V), mirroring
 * `serviceConfigSelection.ts`'s precedent (007). Answers one question: given the
 * architecture's currently-priced selections and the last-accepted Prior Calculation (if
 * any), what should happen to the stored baseline and the "comparison total" a caller
 * derives Price Change from?
 *
 * Deliberately knows nothing about `localStorage`, the snapshot-calculation endpoint, or
 * React state — `WorkspacePage.tsx` (T028) is the only caller and owns all of that.
 */

import type { CalculationDuration, PricingTerm, PurchaseOption } from "../api/client";

/** One SKU selection's pricing inputs, in the same shape the backend's `SnapshotSelection`
 * uses (contracts/api.md) — a plain value, not a reference to a live row. `usage_quantity`
 * is a string (not a number) so two selections compare equal only when their *displayed*
 * quantity is identical, avoiding float-precision false negatives. Using the same enum
 * types `SnapshotSelection` and `SKUSelectionOut` do (rather than raw `string`) means the
 * architecture's live selections and the API's snapshot-request shape both satisfy this
 * interface with no cast. */
export interface PriceChangeSelection {
  service_code: string;
  sku: string;
  pricing_term: PricingTerm;
  purchase_option: PurchaseOption;
  usage_quantity: string;
}

/** The last-accepted Prior Calculation for one Architecture (data-model.md) — persisted
 * per-browser, per-Architecture (FR-016b) by the caller. */
export interface PriorCalculation {
  total: string;
  duration: CalculationDuration;
  selections: PriceChangeSelection[];
}

export type BaselineDecision =
  // No Prior Calculation exists yet for this Architecture — nothing to compare Price Change
  // against, but this calculation becomes the first baseline.
  | "establish"
  // The architecture's contents are unchanged since the Prior Calculation (FR-016) — true
  // whether or not the Duration selection also changed, since Duration alone never counts
  // as a "change" for this purpose. The caller must leave both the stored baseline and
  // whatever Price Change value is currently displayed exactly as they were.
  | "unchanged"
  // Contents changed; Duration did not — Price Change is (new total − prior total) directly
  // (FR-015), and the baseline advances to this calculation.
  | "direct"
  // Contents *and* Duration both changed (FR-016a) — the comparison total must come from
  // recalculating the *prior* selections at the *new* Duration (the snapshot-calculation
  // endpoint), never a direct diff against the un-adjusted prior total. The baseline still
  // advances to this calculation.
  | "duration_adjusted";

/** Two selections are the same content, field-by-field — no `sku_selection_id` in this
 * shape, so identity is entirely by value (data-model.md). */
function selectionKey(s: PriceChangeSelection): string {
  return JSON.stringify([
    s.service_code,
    s.sku,
    s.pricing_term,
    s.purchase_option,
    s.usage_quantity,
  ]);
}

/** Order-independent (multiset) equality — the architecture's contents are "the same" if
 * every selection in one array has a matching selection in the other, regardless of which
 * Collection/Connector each came from or what order iteration produced them in. */
function selectionsEqual(a: PriceChangeSelection[], b: PriceChangeSelection[]): boolean {
  if (a.length !== b.length) return false;
  const aKeys = a.map(selectionKey).sort();
  const bKeys = b.map(selectionKey).sort();
  return aKeys.every((key, i) => key === bKeys[i]);
}

export function decideBaselineUpdate(params: {
  prior: PriorCalculation | null;
  currentSelections: PriceChangeSelection[];
  newDuration: CalculationDuration;
}): BaselineDecision {
  const { prior, currentSelections, newDuration } = params;

  if (prior === null) return "establish";

  const contentChanged = !selectionsEqual(prior.selections, currentSelections);
  if (!contentChanged) return "unchanged";

  const durationChanged = prior.duration !== newDuration;
  return durationChanged ? "duration_adjusted" : "direct";
}
