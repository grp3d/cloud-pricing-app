import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConnectorArrowControls } from "../../src/components/workspace/CollectionsPanel";
import { ARROW_MARKER, connectorMarkers, isDirectional } from "../../src/lib/connectorArrows";

describe("connectorMarkers (019, FR-026, FR-028)", () => {
  it("maps each style to React Flow markers", () => {
    expect(connectorMarkers("none", false)).toEqual({});
    expect(connectorMarkers("one_way", false)).toEqual({ markerEnd: ARROW_MARKER });
    expect(connectorMarkers("two_way", false)).toEqual({
      markerStart: ARROW_MARKER,
      markerEnd: ARROW_MARKER,
    });
    expect(connectorMarkers("one_to_many", false)).toEqual({ markerEnd: ARROW_MARKER });
    expect(connectorMarkers("many_to_one", false)).toEqual({ markerEnd: ARROW_MARKER });
  });

  it("reversing swaps the marker end only, never the path", () => {
    expect(connectorMarkers("one_way", true)).toEqual({ markerStart: ARROW_MARKER });
    expect(connectorMarkers("one_to_many", true)).toEqual({ markerStart: ARROW_MARKER });
    // Not directional: reversing changes nothing.
    expect(connectorMarkers("two_way", true)).toEqual(connectorMarkers("two_way", false));
    expect(connectorMarkers("none", true)).toEqual({});
  });

  it("knows which styles can be reversed", () => {
    expect(["none", "one_way", "two_way"].map((s) => isDirectional(s as never))).toEqual([
      false,
      true,
      false,
    ]);
  });
});

describe("ConnectorArrowControls (019, SC-007)", () => {
  it("sets a style in one click and marks the current one", () => {
    const onChange = vi.fn();
    render(<ConnectorArrowControls style="none" reversed={false} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "None" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Two-way" }));
    expect(onChange).toHaveBeenCalledWith({ arrow_style: "two_way" });
    fireEvent.click(screen.getByRole("button", { name: "None" }));
    expect(onChange).toHaveBeenCalledTimes(1); // already the style: nothing to save
  });

  it("offers Reverse only for a directional arrow, toggling it", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <ConnectorArrowControls style="two_way" reversed={false} onChange={onChange} />,
    );
    expect(screen.getByRole("button", { name: /Reverse/ })).toBeDisabled();
    rerender(<ConnectorArrowControls style="one_way" reversed={true} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /Reverse/ }));
    expect(onChange).toHaveBeenCalledWith({ arrow_reversed: false });
  });
});
