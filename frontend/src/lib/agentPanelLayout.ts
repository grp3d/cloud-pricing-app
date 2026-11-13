/**
 * 023-agent-foundation (clarification 1, research R12, data-model §7): the agent panel's layout
 * in the centre column. A divider splits the column between the canvas area and the panel area
 * (like the inspector's Service/Pricing divider); the panel's bottom-right corner sets its own
 * height inside its area (like the canvas's corner). Saved to the account with the other
 * workspace settings (`workspace.agent_panel`).
 */
import type { WorkspacePreferences } from "../api/client";

export interface AgentPanelLayout {
  open: boolean;
  /** The canvas area's share of the column while the panel is open. */
  split: number;
  /** The panel's own height after a corner resize; null fills its area. */
  height: number | null;
  /** Reserved (the schema allows a width); the panel fills the column's width. */
  width: number | null;
}

export const SPLIT_MIN = 0.2;
export const SPLIT_MAX = 0.8;
export const AGENT_PANEL_MIN_HEIGHT = 120;
export const DEFAULT_AGENT_PANEL: AgentPanelLayout = {
  open: false,
  split: 0.6,
  height: null,
  width: null,
};

export function clampSplit(split: number): number {
  return Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, split));
}

/** The divider moved `deltaY` pixels in a column `columnHeight` pixels tall. */
export function splitAfterDrag(split: number, deltaY: number, columnHeight: number): number {
  if (columnHeight <= 0) return split;
  return clampSplit(split + deltaY / columnHeight);
}

export function clampPanelHeight(height: number, areaHeight: number): number {
  return Math.max(AGENT_PANEL_MIN_HEIGHT, Math.min(height, Math.max(areaHeight, 0)));
}

export function readAgentPanel(
  workspace: WorkspacePreferences | null | undefined,
): AgentPanelLayout {
  const saved = workspace?.agent_panel;
  if (!saved) return DEFAULT_AGENT_PANEL;
  return {
    open: saved.open ?? false,
    split: clampSplit(saved.split ?? DEFAULT_AGENT_PANEL.split),
    height: saved.height ?? null,
    width: saved.width ?? null,
  };
}

export function withAgentPanel(
  workspace: WorkspacePreferences | null | undefined,
  layout: AgentPanelLayout,
): WorkspacePreferences {
  return { ...(workspace ?? {}), agent_panel: { ...layout } };
}
