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
  // Neither the architecture's contents nor the Duration selection changed since the Prior
  // Calculation — a true no-op Calculate (009 corrects 008's original FR-016, which treated a
  // duration-only change as "unchanged" too — see "duration_only" below). The caller must
  // leave both the stored baseline and whatever Price Change value is currently displayed
  // exactly as they were.
  | "unchanged"
  // Contents changed; Duration did not — Price Change is (new total − prior total) directly
  // (FR-015), and the baseline advances to this calculation.
  | "direct"
  // Contents *and* Duration both changed (FR-016a) — the comparison total must come from
  // recalculating the *prior* selections at the *new* Duration (the snapshot-calculation
  // endpoint), never a direct diff against the un-adjusted prior total. The baseline still
  // advances to this calculation.
  | "duration_adjusted"
  // Contents unchanged; Duration alone changed (009-ui-fixes-next-iteration, US2, FR-002/003 —
  // supersedes 008's original "Duration alone never counts as a change" decision, which was the
  // bug: Price Change stayed frozen at the old duration's value). Uses the exact same real
  // recalculation path as "duration_adjusted" (the prior selections, priced at the new
  // Duration via the snapshot-calculation endpoint) — never a client-side ratio multiply, even
  // though the ratio happens to be a simple 12x in this app's two-duration world. The baseline
  // still advances to this calculation, so switching back to the original duration fires this
  // same outcome again (not "unchanged") and naturally restores the original value.
  | "duration_only";

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

/** Order-independent (multiset) equality under `key` — the architecture's contents are "the
 * same" if every entry in one array has a matching entry in the other, regardless of which
 * Collection/Connector each came from or what order iteration produced them in. */
function multisetEqual<T>(a: T[], b: T[], key: (item: T) => string): boolean {
  if (a.length !== b.length) return false;
  const aKeys = a.map(key).sort();
  const bKeys = b.map(key).sort();
  return aKeys.every((k, i) => k === bKeys[i]);
}

function selectionsEqual(a: PriceChangeSelection[], b: PriceChangeSelection[]): boolean {
  return multisetEqual(a, b, selectionKey);
}

/** One priced service as a stored pricing result recorded it (015-canvas-service-icons,
 * data-model.md §4): its pricing inputs plus the region it was priced in — the owning
 * Collection's region, or a Connector's "from" Collection's — since moving a service to a
 * different region changes its price as surely as changing its quantity does. */
export interface PricedContentsEntry extends PriceChangeSelection {
  region: string | null;
}

/** Whether an architecture's current priced contents still match the ones a stored result was
 * calculated from — `false` drives the "Architecture has been updated since last pricing"
 * notice (015, FR-018a, research.md §7). Same multiset semantics as the Price Change baseline
 * comparison, with the region included. */
export function pricedContentsEqual(a: PricedContentsEntry[], b: PricedContentsEntry[]): boolean {
  return multisetEqual(a, b, (e) => JSON.stringify([selectionKey(e), e.region]));
}

export function decideBaselineUpdate(params: {
  prior: PriorCalculation | null;
  currentSelections: PriceChangeSelection[];
  newDuration: CalculationDuration;
}): BaselineDecision {
  const { prior, currentSelections, newDuration } = params;

  if (prior === null) return "establish";

  const contentChanged = !selectionsEqual(prior.selections, currentSelections);
  const durationChanged = prior.duration !== newDuration;

  if (!contentChanged) return durationChanged ? "duration_only" : "unchanged";

  return durationChanged ? "duration_adjusted" : "direct";
}
