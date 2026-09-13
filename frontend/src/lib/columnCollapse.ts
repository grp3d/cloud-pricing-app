/**
 * Per-browser column collapsed/expanded persistence (009-ui-fixes-next-iteration follow-up).
 * Modeled directly on `columnWidths.ts`'s established pattern (same `cloud-pricing-` key
 * prefix, `localStorage`-under-try/catch, never throws, silently no-ops when unavailable) —
 * columns 1-3 (`ProviderArchitecturePanel`/`CollectionsPanel`/`ServiceConfigPanel`) each
 * already own a local `expanded` boolean and its own collapse/expand toggle button; this only
 * adds persistence for that existing state, not a new interaction. Column 4 (the diagram) has
 * no collapsed state of its own (`columnWidths.ts`'s own comment), and column 5 (pricing) has
 * never had one either (008-ui-updates-corrections, FR-011) — so there are only three ids
 * here, not the four `columnWidths.ts` has.
 */

export type CollapsibleColumnId = "provider" | "collections" | "service";

const STORAGE_KEY = "cloud-pricing-column-collapsed";
const COLUMN_IDS: readonly CollapsibleColumnId[] = ["provider", "collections", "service"];

/** Reads whatever collapsed/expanded flags are stored. A missing key, malformed JSON, or an
 * invalid entry for one column never throws — that column simply falls back to its own
 * default (expanded), matching `columnWidths.ts`'s per-entry tolerance. */
export function readColumnCollapsed(): Partial<Record<CollapsibleColumnId, boolean>> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return {};
    const result: Partial<Record<CollapsibleColumnId, boolean>> = {};
    for (const id of COLUMN_IDS) {
      const value = (parsed as Record<string, unknown>)[id];
      if (typeof value === "boolean") result[id] = value;
    }
    return result;
  } catch {
    return {};
  }
}

/** Writes one column's collapsed state, leaving every other stored column untouched.
 * Silently no-ops if `localStorage` is unavailable — the toggle just won't survive a reload
 * this session, matching `columnWidths.ts`'s best-effort persistence. */
export function writeColumnCollapsed(id: CollapsibleColumnId, collapsed: boolean): void {
  try {
    const next = { ...readColumnCollapsed(), [id]: collapsed };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // See comment above — persistence is best-effort.
  }
}
