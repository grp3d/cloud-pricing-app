/**
 * The centre column's Canvas and Agent tabs (023), arranged like the inspector's: merged with
 * one in front (Canvas by default), or split with a divider. Saved to the account as
 * `workspace.center`. Nothing brings Agent forward by itself; a user who wants it always in
 * view splits the pane.
 */
import type { WorkspacePreferences } from "../api/client";
import { type PreferencesStore, preferencesStore } from "./preferences";
import {
  type TabAction,
  type TabArrangement,
  type TabPair,
  nextTabArrangement,
  readTabArrangement,
} from "./tabArrangement";

export type CenterTab = "canvas" | "agent";
export type CenterArrangement = TabArrangement<CenterTab>;
export type CenterAction = TabAction<CenterTab>;

export const CENTER_TABS: TabPair<CenterTab> = ["canvas", "agent"];

export const DEFAULT_CENTER: CenterArrangement = {
  mode: "merged",
  upper: "canvas",
  front: "canvas",
  split: 0.6,
};

/** While the Agent tab is inactive (the agent is off, or a guest), the Canvas is all there is. */
export const CANVAS_ONLY: CenterArrangement = { ...DEFAULT_CENTER };

export function readCenter(workspace: WorkspacePreferences | null | undefined): CenterArrangement {
  return readTabArrangement(CENTER_TABS, workspace?.center, DEFAULT_CENTER);
}

export function nextCenter(current: CenterArrangement, action: CenterAction): CenterArrangement {
  return nextTabArrangement(CENTER_TABS, current, action);
}

/** Saves the arrangement. A PATCH replaces the whole workspace section, so every other
 * workspace field is sent back unchanged. */
export function writeCenter(
  arrangement: CenterArrangement,
  store: PreferencesStore = preferencesStore,
): void {
  store.patchSection("workspace", { ...(store.current.workspace ?? {}), center: arrangement });
}
