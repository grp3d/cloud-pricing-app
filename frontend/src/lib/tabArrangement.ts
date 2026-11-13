/**
 * Two tabs that either share one pane (merged, one in front) or sit in an upper and a lower pane
 * (split), with a movable divider (021's inspector, research R5; 023's centre column). Every
 * change goes through `nextTabArrangement`, a pure function, so split, merge and swap work the
 * same wherever two tabs share a pane.
 */

export type PaneMode = "merged" | "split";

export interface TabArrangement<T extends string> {
  mode: PaneMode;
  /** Split: the tab in the upper pane (the other is below). Kept while merged. */
  upper: T;
  /** Merged: the visible tab. Kept while split. */
  front: T;
  /** Split: the upper pane's share of the height, 0.2 to 0.8. */
  split: number;
}

export type TabAction<T extends string> =
  | { type: "select-tab"; tab: T }
  | { type: "drop-on-lower"; tab: T }
  | { type: "drop-on-upper-bar"; tab: T }
  | { type: "merge"; tab: T }
  | { type: "swap" }
  | { type: "set-split"; split: number };

export const SPLIT_MIN = 0.2;
export const SPLIT_MAX = 0.8;

export type TabPair<T extends string> = readonly [T, T];

export const otherTab = <T extends string>(tabs: TabPair<T>, tab: T): T =>
  tab === tabs[0] ? tabs[1] : tabs[0];

const clampSplit = (value: number) => Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, value));

/** Returns `current` itself when the action changes nothing, so callers can skip a save. */
export function nextTabArrangement<T extends string>(
  tabs: TabPair<T>,
  current: TabArrangement<T>,
  action: TabAction<T>,
): TabArrangement<T> {
  const merged = current.mode === "merged";
  const other = (tab: T) => otherTab(tabs, tab);

  switch (action.type) {
    case "select-tab":
      return !merged || current.front === action.tab ? current : { ...current, front: action.tab };
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

/** The stored arrangement, or `fallback` when none (or an invalid one) is stored. */
export function readTabArrangement<T extends string>(
  tabs: TabPair<T>,
  stored: unknown,
  fallback: TabArrangement<T>,
): TabArrangement<T> {
  const value = stored as Partial<TabArrangement<T>> | null | undefined;
  const isTab = (v: unknown): v is T => v === tabs[0] || v === tabs[1];
  if (
    value &&
    (value.mode === "merged" || value.mode === "split") &&
    isTab(value.upper) &&
    isTab(value.front) &&
    typeof value.split === "number" &&
    value.split >= SPLIT_MIN &&
    value.split <= SPLIT_MAX
  ) {
    return { mode: value.mode, upper: value.upper, front: value.front, split: value.split };
  }
  return fallback;
}
