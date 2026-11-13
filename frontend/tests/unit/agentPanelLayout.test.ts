import { describe, expect, it } from "vitest";

import {
  AGENT_PANEL_MIN_HEIGHT,
  DEFAULT_AGENT_PANEL,
  clampPanelHeight,
  clampSplit,
  readAgentPanel,
  splitAfterDrag,
  withAgentPanel,
} from "../../src/lib/agentPanelLayout";

describe("agent panel layout", () => {
  it("keeps the divider between 20% and 80% of the column", () => {
    expect(clampSplit(0.1)).toBe(0.2);
    expect(clampSplit(0.95)).toBe(0.8);
    expect(clampSplit(0.55)).toBe(0.55);
  });

  it("moves the divider by the dragged distance", () => {
    expect(splitAfterDrag(0.6, 100, 1000)).toBeCloseTo(0.7);
    expect(splitAfterDrag(0.6, -1000, 1000)).toBe(0.2);
    expect(splitAfterDrag(0.6, 50, 0)).toBe(0.6);
  });

  it("keeps the corner-resized height at least the minimum and within its area", () => {
    expect(clampPanelHeight(50, 400)).toBe(AGENT_PANEL_MIN_HEIGHT);
    expect(clampPanelHeight(900, 400)).toBe(400);
    expect(clampPanelHeight(250, 400)).toBe(250);
  });

  it("reads the saved layout, with defaults when there is none", () => {
    expect(readAgentPanel(null)).toEqual(DEFAULT_AGENT_PANEL);
    expect(readAgentPanel({ agent_panel: { open: true, split: 0.5, height: 300 } })).toEqual({
      open: true,
      split: 0.5,
      height: 300,
      width: null,
    });
  });

  it("writes the layout into the workspace section without touching the rest", () => {
    const workspace = { last_provider: "gcp" as const };
    expect(withAgentPanel(workspace, { ...DEFAULT_AGENT_PANEL, open: true })).toEqual({
      last_provider: "gcp",
      agent_panel: { open: true, split: 0.6, height: null, width: null },
    });
  });
});
