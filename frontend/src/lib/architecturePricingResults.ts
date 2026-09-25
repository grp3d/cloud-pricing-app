/**
 * Per-browser, per-Architecture stored pricing results (015-canvas-service-icons, US4,
 * FR-015-FR-022, data-model.md §5, research.md §6) — what column 5 shows for the *active*
 * Architecture, instead of whichever calculation happened to run last. Same
 * `localStorage`-under-try/catch + type-guard pattern as `priorCalculation.ts`: a missing,
 * malformed, or older-shape entry is never an error, just "no stored result yet" (which
 * triggers an automatic calculation). Stored results are verbatim `calculate` responses —
 * nothing here computes a price (Constitution Principle I) — and never reach Postgres
 * (Principle II).
 *
 * `applyCalculationSuccess` and `shouldAutoCalculate` are the pure decisions
 * `WorkspacePage.tsx` makes around a calculation, extracted so they're test-first (Principle
 * V): in particular, a result is always recorded under the Architecture it was *requested*
 * for, using only the context captured at request time (FR-020).
 */

import type { CalculationDuration, CalculationResult } from "../api/client";
import type {
  BaselineDecision,
  PriceChangeSelection,
  PricedContentsEntry,
  PriorCalculation,
} from "./priceChange";

export interface PricingResultEntry {
  /** Shape version — any other value reads as "no stored result". */
  version: 1;
  result: CalculationResult;
  /** The Duration this result was calculated at (FR-018b restores the dropdown to it). */
  duration: CalculationDuration;
  /** The Price Change displayed alongside this result, if any (FR-022). */
  priceChange: string | null;
  /** What was priced — compared against the live architecture for FR-018a's notice. */
  pricedContents: PricedContentsEntry[];
  /** ISO-8601; informational only. */
  calculatedAt: string;
}

function storageKey(architectureId: string): string {
  return `cloud-pricing-result-${architectureId}`;
}

function isPricingResultEntry(value: unknown): value is PricingResultEntry {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    v.version === 1 &&
    typeof v.result === "object" &&
    v.result !== null &&
    typeof (v.result as Record<string, unknown>).total_price === "string" &&
    typeof v.duration === "string" &&
    (v.priceChange === null || typeof v.priceChange === "string") &&
    Array.isArray(v.pricedContents)
  );
}

export function readPricingResult(architectureId: string): PricingResultEntry | null {
  try {
    const raw = localStorage.getItem(storageKey(architectureId));
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isPricingResultEntry(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function writePricingResult(architectureId: string, entry: PricingResultEntry): void {
  try {
    localStorage.setItem(storageKey(architectureId), JSON.stringify(entry));
  } catch {
    // Best-effort persistence — see the module comment.
  }
}

export function removePricingResult(architectureId: string): void {
  try {
    localStorage.removeItem(storageKey(architectureId));
  } catch {
    // Best-effort, as above.
  }
}

/** FR-017: calculate automatically only for an Architecture that has something to price, no
 * stored result, no request already on its way, and no failed attempt currently showing — after
 * a failure, retrying is the user's call (the existing Retry control), never an automatic loop. */
export function shouldAutoCalculate(params: {
  architectureId: string | undefined;
  hasSelections: boolean;
  hasStoredEntry: boolean;
  isInFlight: boolean;
  hasError: boolean;
}): boolean {
  const { architectureId, hasSelections, hasStoredEntry, isInFlight, hasError } = params;
  return Boolean(architectureId) && hasSelections && !hasStoredEntry && !isInFlight && !hasError;
}

/** Everything a calculation needs to be recorded correctly, captured when it was *requested*
 * — never read back from current state when the response arrives (FR-020). */
export interface CalculationRequestVars {
  architectureId: string;
  duration: CalculationDuration;
  pricedContents: PricedContentsEntry[];
  priceChangeSelections: PriceChangeSelection[];
  /** That Architecture's Price Change baseline at request time. */
  prior: PriorCalculation | null;
}

/** Records a successful calculation: the new stored entry for `vars.architectureId` (every
 * other Architecture's entry untouched), and the Price Change baseline to persist, if any.
 *
 * - `"establish"`: no Price Change yet; the result becomes the first baseline.
 * - `"direct"` / `"duration_adjusted"` / `"duration_only"`: Price Change = new total −
 *   `comparisonTotal` (the caller supplies the prior total, or its real repricing at the new
 *   Duration), and the baseline advances.
 * - `"unchanged"`: a true no-op recalculation — the previously displayed Price Change carries
 *   forward and the baseline is left exactly as it was (`newBaseline: null`). */
export function applyCalculationSuccess(params: {
  entries: ReadonlyMap<string, PricingResultEntry>;
  vars: CalculationRequestVars;
  result: CalculationResult;
  decision: BaselineDecision;
  comparisonTotal: string | null;
  previousEntry: PricingResultEntry | undefined;
  now: string;
}): {
  entries: Map<string, PricingResultEntry>;
  entry: PricingResultEntry;
  newBaseline: PriorCalculation | null;
} {
  const { entries, vars, result, decision, comparisonTotal, previousEntry, now } = params;

  let priceChange: string | null;
  let newBaseline: PriorCalculation | null;
  if (decision === "unchanged") {
    priceChange = previousEntry?.priceChange ?? null;
    newBaseline = null;
  } else {
    priceChange =
      decision === "establish" || comparisonTotal === null
        ? null
        : String(Number(result.total_price) - Number(comparisonTotal));
    newBaseline = {
      total: result.total_price,
      duration: vars.duration,
      selections: vars.priceChangeSelections,
    };
  }

  const entry: PricingResultEntry = {
    version: 1,
    result,
    duration: vars.duration,
    priceChange,
    pricedContents: vars.pricedContents,
    calculatedAt: now,
  };
  const next = new Map(entries);
  next.set(vars.architectureId, entry);
  return { entries: next, entry, newBaseline };
}
