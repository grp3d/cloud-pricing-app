/**
 * Column widths (008-ui-updates-corrections, FR-013), saved to the user's account since 019
 * (FR-023): the `workspace.column_widths` preferences section, keys `col1` to `col4` in column
 * order. Widths an earlier version saved in this browser are used until they are moved to the
 * account, once (FR-024, `preferences.ts`).
 *
 * Column 4 (the diagram) already has its own independent height-resize handle and grows to
 * fill remaining width by default, so it isn't a *fixed* width preference the way the other
 * four columns are — there's no `"diagram"` entry here.
 */
import type { ColumnKey } from "./browserPrefs";
import {
  type PreferencesStore,
  effectiveWorkspace,
  preferencesStore,
  usePreferences,
} from "./preferences";

export type ColumnId = "provider" | "collections" | "service" | "pricing";

const KEYS: Record<ColumnId, ColumnKey> = {
  provider: "col1",
  collections: "col2",
  service: "col3",
  pricing: "col4",
};

/** Each column's width before this feature introduced dragging (007's hardcoded Tailwind
 * `w-64`/`w-80`/`w-72`/`w-72` classes) — used by `WorkspacePage.tsx` as the starting width
 * for a user who has never stored a preference. */
export const DEFAULT_WIDTHS: Record<ColumnId, number> = {
  provider: 256,
  collections: 320,
  service: 288,
  pricing: 288,
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
