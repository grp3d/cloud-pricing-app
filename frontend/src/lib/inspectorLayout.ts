/**
 * The workspace inspector's tab arrangement (021, research R5, data-model §1): Pricing and
 * Service either share one pane (merged, one tab in front) or sit in an upper and a lower pane
 * (split). Every change goes through `nextArrangement`, a pure function, so the rules for
 * which tab comes forward (FR-015 to FR-017) and for split, merge and swap (FR-019 to FR-023)
 * live in one tested place. The arrangement is saved to the account as `workspace.inspector`
 * (FR-024).
 */
import type { WorkspacePreferences } from "../api/client";
import { type PreferencesStore, preferencesStore } from "./preferences";

export type InspectorTab = "pricing" | "service";
export type InspectorMode = "merged" | "split";

export interface InspectorArrangement {
  mode: InspectorMode;
  /** Split: the tab in the upper pane (the other is below). Kept while merged. */
  upper: InspectorTab;
  /** Merged: the visible tab. Kept while split. */
  front: InspectorTab;
  /** Split: the upper pane's share of the height, 0.2 to 0.8. */
  split: number;
}

export type InspectorAction =
  | { type: "select-tab"; tab: InspectorTab }
  | { type: "drop-on-lower"; tab: InspectorTab }
  | { type: "drop-on-upper-bar"; tab: InspectorTab }
  | { type: "merge"; tab: InspectorTab }
  | { type: "swap" }
  | { type: "set-split"; split: number }
  | { type: "service-selected" }
  | { type: "calculation-finished" };

export const SPLIT_MIN = 0.2;
export const SPLIT_MAX = 0.8;

export const DEFAULT_ARRANGEMENT: InspectorArrangement = {
  mode: "merged",
  upper: "pricing",
  front: "pricing",
  split: 0.5,
};

export const other = (tab: InspectorTab): InspectorTab =>
  tab === "pricing" ? "service" : "pricing";

const clampSplit = (value: number) => Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, value));

/** Returns `current` itself when the action changes nothing, so callers can skip a save. */
export function nextArrangement(
  current: InspectorArrangement,
  action: InspectorAction,
): InspectorArrangement {
  const merged = current.mode === "merged";
  const withFront = (front: InspectorTab) =>
    current.front === front ? current : { ...current, front };

  switch (action.type) {
    case "select-tab":
      return merged ? withFront(action.tab) : current;
    case "service-selected":
      return merged ? withFront("service") : current;
    case "calculation-finished":
      return merged ? withFront("pricing") : current;
    case "drop-on-lower":
      if (merged) return { ...current, mode: "split", upper: other(action.tab) };
      // Split: dropping the upper tab below swaps the panes; the lower tab is already there.
      return current.upper === action.tab ? { ...current, upper: other(action.tab) } : current;
    case "drop-on-upper-bar":
    case "merge":
      return merged ? current : { ...current, mode: "merged", front: action.tab };
    case "swap":
      return merged ? current : { ...current, upper: other(current.upper) };
    case "set-split": {
      if (merged) return current;
      const value = clampSplit(action.split);
      return value === current.split ? current : { ...current, split: value };
    }
  }
}

const isTab = (v: unknown): v is InspectorTab => v === "pricing" || v === "service";

/** The stored arrangement, or the default when none (or an invalid one) is stored. */
export function readInspector(
  workspace: WorkspacePreferences | null | undefined,
): InspectorArrangement {
  const stored = workspace?.inspector as Partial<InspectorArrangement> | null | undefined;
  if (
    stored &&
    (stored.mode === "merged" || stored.mode === "split") &&
    isTab(stored.upper) &&
    isTab(stored.front) &&
    typeof stored.split === "number" &&
    stored.split >= SPLIT_MIN &&
    stored.split <= SPLIT_MAX
  ) {
    return { mode: stored.mode, upper: stored.upper, front: stored.front, split: stored.split };
  }
  return DEFAULT_ARRANGEMENT;
}

/** Saves the arrangement. A PATCH replaces the whole workspace section, so every other
 * workspace field (widths, collapsed, last provider) is sent back unchanged. */
export function writeInspector(
  arrangement: InspectorArrangement,
  store: PreferencesStore = preferencesStore,
): void {
  store.patchSection("workspace", { ...(store.current.workspace ?? {}), inspector: arrangement });
}
