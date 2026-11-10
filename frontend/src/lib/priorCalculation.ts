/**
 * Per-browser, per-Architecture Prior Calculation persistence (US5, FR-016b, data-model.md)
 * — the baseline `priceChange.ts`'s `decideBaselineUpdate` compares against. Same
 * `localStorage`-under-try/catch pattern as `columnWidths.ts`/`api/client.ts`'s
 * `getUserId()`: a missing or malformed entry is never an error, just "no baseline yet".
 */

import { isStoredSelection, type PriorCalculation } from "./priceChange";

function storageKey(architectureId: string): string {
  return `cloud-pricing-prior-calculation-${architectureId}`;
}

function isPriorCalculation(value: unknown): value is PriorCalculation {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  // 020 (data-model §3): `version: 2`, or no version at all (a legacy v0.0.2 baseline).
  return (
    (v.version === undefined || v.version === 2) &&
    typeof v.total === "string" &&
    typeof v.duration === "string" &&
    Array.isArray(v.selections) &&
    v.selections.every(isStoredSelection)
  );
}

export function readPriorCalculation(architectureId: string): PriorCalculation | null {
  try {
    const raw = localStorage.getItem(storageKey(architectureId));
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isPriorCalculation(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function writePriorCalculation(architectureId: string, value: PriorCalculation): void {
  try {
    localStorage.setItem(storageKey(architectureId), JSON.stringify(value));
  } catch {
    // Best-effort persistence — see comment above.
  }
}
