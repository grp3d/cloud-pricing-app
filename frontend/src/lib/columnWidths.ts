/**
 * Column widths (008-ui-updates-corrections, FR-013), saved to the user's account since 019
 * (FR-023): the `workspace.column_widths` preferences section, keys `col1` to `col4` in column
 * order. Widths an earlier version saved in this browser are used until they are moved to the
 * account, once (FR-024, `preferences.ts`).
 *
 * 021 (FR-010, FR-011): the workspace has three zones; only the two side zones have widths.
 * The Architecture Editor sidebar keeps `col2`, and the inspector takes over the Price
 * Summary's `col4`, so saved widths carry over. `col1` and `col3` (the removed columns) are no
 * longer read. The canvas fills the rest, so it has no entry here.
 */
import type { ColumnKey } from "./browserPrefs";
import {
  type PreferencesStore,
  effectiveWorkspace,
  preferencesStore,
  usePreferences,
} from "./preferences";

export type ColumnId = "collections" | "inspector";

const KEYS: Record<ColumnId, ColumnKey> = {
  // col1 (the removed Column 1, 021) is no longer read; a stored value is left in place.
  collections: "col2",
  // col3 (the removed Service Editor column, 021) is no longer read either.
  // 021: the inspector (Pricing and Service tabs) takes over the Price Summary's key, so a
  // saved Price Summary width carries over (FR-011).
  inspector: "col4",
};

/** Each column's width before this feature introduced dragging (007's hardcoded Tailwind
 * `w-64`/`w-80`/`w-72`/`w-72` classes) — used by `WorkspacePage.tsx` as the starting width
 * for a user who has never stored a preference. */
export const DEFAULT_WIDTHS: Record<ColumnId, number> = {
  collections: 320,
  inspector: 360,
};

/** No column may be dragged narrower than its own collapsed-rail width (research.md §9) —
 * matches the `w-14` (56px) rail every panel already collapses to via its own toggle. */
export const MIN_WIDTH = 56;

/** The stored widths; a column with no valid stored width is left out (its default
 * applies). */
export function readColumnWidths(
  store: PreferencesStore = preferencesStore,
): Partial<Record<ColumnId, number>> {
  const stored = effectiveWorkspace(store.current, store.readBrowser).column_widths ?? {};
  const result: Partial<Record<ColumnId, number>> = {};
  for (const [id, key] of Object.entries(KEYS) as [ColumnId, ColumnKey][]) {
    const value = stored[key];
    if (typeof value === "number" && Number.isFinite(value) && value > 0) result[id] = value;
  }
  return result;
}

/** Saves one column's width, leaving every other column untouched. It applies at once; a
 * failed save is retried in the background and never breaks the resize (FR-025). */
export function writeColumnWidth(
  id: ColumnId,
  width: number,
  store: PreferencesStore = preferencesStore,
): void {
  const workspace = store.current.workspace ?? {};
  store.patchSection("workspace", {
    ...workspace,
    column_widths: { ...workspace.column_widths, [KEYS[id]]: Math.round(width) },
  });
}

/** The stored widths, re-rendering when they change (including when the account's values
 * arrive after the first render). */
export function useColumnWidths(
  store: PreferencesStore = preferencesStore,
): Partial<Record<ColumnId, number>> {
  usePreferences(store);
  return readColumnWidths(store);
}
