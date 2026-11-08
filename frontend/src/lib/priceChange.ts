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

import type {
  CalculationDuration,
  PricingTerm,
  ProviderCode,
  ProviderOptions,
  PurchaseOption,
} from "../api/client";

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
  /** 020 (research R1): the region the selection is priced in — its box's, or a connector's
   * "from" box's. Absent on legacy (v0.0.2) baselines. */
  region?: string | null;
  /** 020: GCP machine vCPUs/memory or Azure VM OS. Absent on legacy baselines. */
  provider_options?: ProviderOptions | null;
}

/** The last-accepted Prior Calculation for one Architecture (data-model.md) — persisted
 * per-browser, per-Architecture (FR-016b) by the caller. 020 (data-model §3): `version: 2`
 * baselines carry each selection's region and options; one with no `version` is legacy. */
export interface PriorCalculation {
  version?: 2;
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
  | "duration_only"
  // 020 (FR-005, research R3): a legacy (v0.0.2) baseline on a GCP or Azure architecture, and
  // the Duration changed. The baseline has no regions or options, so the previous contents
  // can't be re-priced faithfully: Price Change shows "Not available" instead of a number.
  // The baseline still advances (as version 2), so the next calculation is exact.
  | "unavailable";

/** Two selections are the same content, field-by-field — no `sku_selection_id` in this
 * shape, so identity is entirely by value (data-model.md). This is the original five-field
 * key, still used on its own for legacy baselines (020, research R3). */
function selectionKey(s: PriceChangeSelection): string {
  return JSON.stringify([
    s.service_code,
    s.sku,
    s.pricing_term,
    s.purchase_option,
    s.usage_quantity,
  ]);
}

/** 020 (data-model §3): options in a canonical form — JSON with sorted keys, or `null` — so the
 * same values in a different key order, or edited and put back, compare equal. */
function optionsKey(options: ProviderOptions | null | undefined): string | null {
  if (options == null) return null;
  const record = options as Record<string, unknown>;
  return JSON.stringify(
    Object.keys(record)
      .sort()
      .map((k) => [k, record[k]]),
  );
}

/** 020: the full comparison key for version 2 baselines — every input a price depends on. */
function fullSelectionKey(s: PriceChangeSelection): string {
  return JSON.stringify([selectionKey(s), s.region ?? null, optionsKey(s.provider_options)]);
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

function selectionsEqual(
  a: PriceChangeSelection[],
  b: PriceChangeSelection[],
  key: (s: PriceChangeSelection) => string,
): boolean {
  return multisetEqual(a, b, key);
}

/** One priced service as a stored pricing result recorded it (015-canvas-service-icons,
 * data-model.md §4): its pricing inputs plus the region it was priced in — the owning
 * Collection's region, or a Connector's "from" Collection's — since moving a service to a
 * different region changes its price as surely as changing its quantity does. */
export interface PricedContentsEntry extends PriceChangeSelection {
  region: string | null;
}

/** 020 (data-model §4): an entry stored before this feature has no `provider_options` field. */
function isLegacyEntry(e: PricedContentsEntry): boolean {
  return !("provider_options" in e);
}

/** Whether an architecture's current priced contents still match the ones a stored result was
 * calculated from — `false` drives the "Architecture has been updated since last pricing"
 * notice (015, FR-018a, research.md §7). Same multiset semantics as the Price Change baseline
 * comparison, with the region included. 020: options are compared too, unless either side
 * holds legacy entries (no `provider_options` field), so the upgrade alone never shows the
 * notice. */
export function pricedContentsEqual(a: PricedContentsEntry[], b: PricedContentsEntry[]): boolean {
  const withOptions = !a.some(isLegacyEntry) && !b.some(isLegacyEntry);
  return multisetEqual(a, b, (e) =>
    JSON.stringify([
      selectionKey(e),
      e.region ?? null,
      withOptions ? optionsKey(e.provider_options) : null,
    ]),
  );
}

/** 020 (T009/T010): a stored selection is readable — the five string fields, plus an optional
 * `region` (string or null) and optional `provider_options` (object or null). Shared by the
 * baseline and stored-result type guards, so unreadable entries are dropped, never compared. */
export function isStoredSelection(value: unknown): value is PriceChangeSelection {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  const strings = ["service_code", "sku", "pricing_term", "purchase_option", "usage_quantity"];
  if (!strings.every((k) => typeof v[k] === "string")) return false;
  if ("region" in v && v.region !== null && typeof v.region !== "string") return false;
  if (
    "provider_options" in v &&
    v.provider_options !== null &&
    (typeof v.provider_options !== "object" || Array.isArray(v.provider_options))
  ) {
    return false;
  }
  return true;
}

/** Whether a baseline was stored before 020 (no `version`), data-model §3. */
export function isLegacyBaseline(prior: PriorCalculation): boolean {
  return prior.version !== 2;
}

export function decideBaselineUpdate(params: {
  prior: PriorCalculation | null;
  currentSelections: PriceChangeSelection[];
  newDuration: CalculationDuration;
  /** 020: the architecture's provider. Missing means `aws`. */
  provider?: ProviderCode;
}): BaselineDecision {
  const { prior, currentSelections, newDuration, provider = "aws" } = params;

  if (prior === null) return "establish";

  const legacy = isLegacyBaseline(prior);
  const contentChanged = !selectionsEqual(
    prior.selections,
    currentSelections,
    legacy ? selectionKey : fullSelectionKey,
  );
  const durationChanged = prior.duration !== newDuration;

  // 020 (FR-005): a legacy GCP or Azure baseline can't be re-priced at another Duration.
  if (legacy && durationChanged && provider !== "aws") return "unavailable";

  if (!contentChanged) return durationChanged ? "duration_only" : "unchanged";

  return durationChanged ? "duration_adjusted" : "direct";
}
