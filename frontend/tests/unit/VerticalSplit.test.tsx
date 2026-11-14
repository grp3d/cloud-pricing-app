import { act, fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { VerticalSplit } from "../../src/components/layout/VerticalSplit";

/** 024 FR-018 (contracts/results-pane-ui.md "Layout"). */

let resize: ((width: number) => void) | null = null;

beforeAll(() => {
  Element.prototype.setPointerCapture ??= () => {};
  class FakeResizeObserver {
    constructor(private callback: ResizeObserverCallback) {}
    observe() {
      resize = (width) =>
        this.callback(
          [{ contentRect: { width } } as ResizeObserverEntry],
          this as unknown as ResizeObserver,
        );
    }
    disconnect() {}
    unobserve() {}
  }
  globalThis.ResizeObserver = FakeResizeObserver as unknown as typeof ResizeObserver;
});

afterEach(() => {
  resize = null;
});

function renderSplit(onCommit = vi.fn(), second: React.ReactNode | null = <p>Results</p>) {
  render(
    <VerticalSplit
      first={<p>Conversation</p>}
      second={second}
      split={0.45}
      min={0.3}
      max={0.75}
      onCommit={onCommit}
      label="Resize conversation and results"
    />,
  );
  act(() => resize?.(1000));
  return onCommit;
}

describe("VerticalSplit", () => {
  it("is a vertical separator with its value", () => {
    renderSplit();
    const divider = screen.getByRole("separator", { name: "Resize conversation and results" });
    expect(divider).toHaveAttribute("aria-orientation", "vertical");
    expect(divider).toHaveAttribute("aria-valuenow", "45");
    expect(divider).toHaveAttribute("aria-valuemin", "30");
    expect(divider).toHaveAttribute("aria-valuemax", "75");
  });

  it("moves 5% a key press within the limits, and Home and End go to the limits", () => {
    const onCommit = renderSplit();
    const divider = screen.getByRole("separator");
    fireEvent.keyDown(divider, { key: "ArrowRight" });
    fireEvent.keyDown(divider, { key: "ArrowLeft" });
    fireEvent.keyDown(divider, { key: "Home" });
    fireEvent.keyDown(divider, { key: "End" });
    expect(onCommit.mock.calls.map((c) => c[0])).toEqual([0.5, 0.4, 0.3, 0.75]);
  });

  it("commits a drag on release, clamped", () => {
    const onCommit = renderSplit();
    const divider = screen.getByRole("separator");
    const container = divider.parentElement as HTMLElement;
    container.getBoundingClientRect = () =>
      ({ left: 0, width: 1000, top: 0, height: 500 }) as DOMRect;
    // jsdom has no PointerEvent: mouse events carry the coordinates under pointer names.
    const fire = (type: string, x: number) =>
      divider.dispatchEvent(new MouseEvent(type, { bubbles: true, clientX: x, button: 0 }));
    act(() => {
      fire("pointerdown", 450);
      fire("pointermove", 900);
      fire("pointerup", 900);
    });
    expect(onCommit).toHaveBeenCalledWith(0.75);
  });

  it("stacks the second pane below the first when narrow", () => {
    renderSplit();
    act(() => resize?.(600));
    expect(screen.queryByRole("separator")).toBeNull();
    expect(screen.getByText("Conversation")).toBeInTheDocument();
    expect(screen.getByText("Results")).toBeInTheDocument();
    act(() => resize?.(800));
    expect(screen.getByRole("separator")).toBeInTheDocument();
  });

  it("never remounts the first pane when the layout changes", () => {
    let mounts = 0;
    function Counted() {
      const [id] = React.useState(() => ++mounts);
      return <p>Conversation {id}</p>;
    }
    const { rerender } = render(
      <VerticalSplit first={<Counted />} second={null} split={0.45} min={0.3} max={0.75}
        onCommit={vi.fn()} label="Resize" />,
    );
    act(() => resize?.(1000));
    rerender(
      <VerticalSplit first={<Counted />} second={<p>Results</p>} split={0.45} min={0.3}
        max={0.75} onCommit={vi.fn()} label="Resize" />,
    );
    act(() => resize?.(600));
    act(() => resize?.(900));
    expect(mounts).toBe(1);
  });

  it("without a second pane the first fills the space", () => {
    renderSplit(vi.fn(), null);
    expect(screen.queryByRole("separator")).toBeNull();
    expect(screen.getByText("Conversation")).toBeInTheDocument();
  });
});
