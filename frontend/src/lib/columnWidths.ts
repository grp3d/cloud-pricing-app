/**
 * Per-browser column-width persistence (008-ui-updates-corrections, FR-013, research.md
 * §7). Uses `localStorage` directly, under the same `cloud-pricing-` key prefix the
 * existing anonymous per-browser user id already uses (`frontend/src/api/client.ts`'s
 * `getUserId()`) — no new persistence mechanism, no backend involvement (Clarifications).
 *
 * Column 4 (the diagram) already has its own independent height-resize handle and grows to
 * fill remaining width by default, so it isn't a *fixed* width preference the way the other
 * four columns are — there's no `"diagram"` entry here.
 */

export type ColumnId = "provider" | "collections" | "service" | "pricing";

const STORAGE_KEY = "cloud-pricing-column-widths";
const COLUMN_IDS: readonly ColumnId[] = ["provider", "collections", "service", "pricing"];

/** Each column's width before this feature introduced dragging (007's hardcoded Tailwind
 * `w-64`/`w-80`/`w-72`/`w-72` classes) — used by `WorkspacePage.tsx` as the starting width
 * for a browser that has never stored a preference. */
export const DEFAULT_WIDTHS: Record<ColumnId, number> = {
  provider: 256,
  collections: 320,
  service: 288,
  pricing: 288,
};

/** No column may be dragged narrower than its own collapsed-rail width (research.md §9) —
 * matches the `w-14` (56px) rail every panel already collapses to via its own toggle. */
export const MIN_WIDTH = 56;

/** Reads whatever column widths are stored. A missing key, malformed JSON, or an invalid
 * entry for one column never throws — each column simply falls back to its own default,
 * matching this codebase's existing `localStorage` read pattern (`getUserId()`). */
export function readColumnWidths(): Partial<Record<ColumnId, number>> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return {};
    const result: Partial<Record<ColumnId, number>> = {};
    for (const id of COLUMN_IDS) {
      const value = (parsed as Record<string, unknown>)[id];
      if (typeof value === "number" && Number.isFinite(value) && value > 0) {
        result[id] = value;
      }
    }
    return result;
  } catch {
    return {};
  }
}

/** Writes one column's width, leaving every other stored column untouched. Silently no-ops
 * if `localStorage` is unavailable (private browsing, quota, etc.) — the width just won't
 * persist this session rather than breaking the resize interaction itself. */
export function writeColumnWidth(id: ColumnId, width: number): void {
  try {
    const next = { ...readColumnWidths(), [id]: width };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // See comment above — persistence is best-effort.
  }
}
