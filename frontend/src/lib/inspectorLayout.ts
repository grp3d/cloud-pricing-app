/**
 * The workspace inspector's tab arrangement (021, research R5, data-model §1): Pricing and
 * Service either share one pane (merged, one tab in front) or sit in an upper and a lower pane
 * (split). Every change goes through `nextArrangement`, a pure function, so the rules for
 * which tab comes forward (FR-015 to FR-017) and for split, merge and swap (FR-019 to FR-023)
 * live in one tested place (023: the shared two-tab rules are in `tabArrangement.ts`). The arrangement is saved to the account as `workspace.inspector`
 * (FR-024).
 */
import type { WorkspacePreferences } from "../api/client";
import { type PreferencesStore, preferencesStore } from "./preferences";
import {
  type PaneMode,
  SPLIT_MAX,
  SPLIT_MIN,
  type TabAction,
  type TabArrangement,
  type TabPair,
  nextTabArrangement,
  otherTab,
  readTabArrangement,
} from "./tabArrangement";

export type InspectorTab = "pricing" | "service";
export type InspectorMode = PaneMode;
export type InspectorArrangement = TabArrangement<InspectorTab>;

export type InspectorAction =
  TabAction<InspectorTab> | { type: "service-selected" } | { type: "calculation-finished" };

export { SPLIT_MAX, SPLIT_MIN };

export const INSPECTOR_TABS: TabPair<InspectorTab> = ["pricing", "service"];

export const DEFAULT_ARRANGEMENT: InspectorArrangement = {
  mode: "merged",
  upper: "pricing",
  front: "pricing",
  split: 0.5,
};

export const other = (tab: InspectorTab): InspectorTab => otherTab(INSPECTOR_TABS, tab);

/** Returns `current` itself when the action changes nothing, so callers can skip a save. The
 * inspector's own rules: selecting a service brings Service forward, and a finished
 * calculation brings Pricing forward (FR-015, FR-016); everything else is shared. */
export function nextArrangement(
  current: InspectorArrangement,
  action: InspectorAction,
): InspectorArrangement {
  if (action.type === "service-selected") {
    return nextTabArrangement(INSPECTOR_TABS, current, { type: "select-tab", tab: "service" });
  }
  if (action.type === "calculation-finished") {
    return nextTabArrangement(INSPECTOR_TABS, current, { type: "select-tab", tab: "pricing" });
  }
  return nextTabArrangement(INSPECTOR_TABS, current, action);
}

/** The stored arrangement, or the default when none (or an invalid one) is stored. */
export function readInspector(
  workspace: WorkspacePreferences | null | undefined,
): InspectorArrangement {
  return readTabArrangement(INSPECTOR_TABS, workspace?.inspector, DEFAULT_ARRANGEMENT);
}

/** Saves the arrangement. A PATCH replaces the whole workspace section, so every other
 * workspace field (widths, collapsed, last provider) is sent back unchanged. */
export function writeInspector(
  arrangement: InspectorArrangement,
  store: PreferencesStore = preferencesStore,
): void {
  store.patchSection("workspace", { ...(store.current.workspace ?? {}), inspector: arrangement });
}
