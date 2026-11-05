/**
 * Collapsed columns (009-ui-fixes-next-iteration follow-up), saved to the user's account since
 * 019 (FR-023): the `workspace.collapsed` preferences section, keys `col1` to `col3`. Values an
 * earlier version saved in this browser are used until they are moved to the account, once
 * (FR-024, `preferences.ts`). Column 4 (the diagram) and column 5 (pricing) have no collapsed
 * state, so there are only three ids here.
 */
import type { ColumnKey } from "./browserPrefs";
import {
  type PreferencesStore,
  effectiveWorkspace,
  preferencesStore,
  usePreferences,
} from "./preferences";

export type CollapsibleColumnId = "provider" | "collections" | "service";

const KEYS: Record<CollapsibleColumnId, ColumnKey> = {
  provider: "col1",
  collections: "col2",
  service: "col3",
};

/** The stored collapsed flags; a column with no stored flag is left out (expanded). */
export function readColumnCollapsed(
  store: PreferencesStore = preferencesStore,
): Partial<Record<CollapsibleColumnId, boolean>> {
  const stored = effectiveWorkspace(store.current, store.readBrowser).collapsed ?? {};
  const result: Partial<Record<CollapsibleColumnId, boolean>> = {};
  for (const [id, key] of Object.entries(KEYS) as [CollapsibleColumnId, ColumnKey][]) {
    const value = stored[key];
    if (typeof value === "boolean") result[id] = value;
  }
  return result;
}

/** Saves one column's collapsed state, leaving every other column untouched. */
export function writeColumnCollapsed(
  id: CollapsibleColumnId,
  collapsed: boolean,
  store: PreferencesStore = preferencesStore,
): void {
  const workspace = store.current.workspace ?? {};
  store.patchSection("workspace", {
    ...workspace,
    collapsed: { ...workspace.collapsed, [KEYS[id]]: collapsed },
  });
}

/** The stored collapsed flags, re-rendering when they change. */
export function useColumnCollapsed(
  store: PreferencesStore = preferencesStore,
): Partial<Record<CollapsibleColumnId, boolean>> {
  usePreferences(store);
  return readColumnCollapsed(store);
}
