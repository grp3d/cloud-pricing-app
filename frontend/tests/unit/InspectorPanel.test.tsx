import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "../../src/components/ui/tooltip";
import {
  InspectorPanel,
  type InspectorPanelProps,
} from "../../src/components/workspace/InspectorPanel";
import {
  DEFAULT_ARRANGEMENT,
  type InspectorAction,
  type InspectorArrangement,
  nextArrangement,
} from "../../src/lib/inspectorLayout";

/** 021 US2 and US3 (contracts/ui.md "Inspector"). */

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => {};
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
});

function ServiceForm() {
  return <input aria-label="vCPUs" defaultValue="2" />;
}

function renderPanel(overrides: Partial<InspectorPanelProps> = {}) {
  const onAction = vi.fn();
  const props: InspectorPanelProps = {
    arrangement: DEFAULT_ARRANGEMENT,
    onAction,
    collapsed: false,
    onCollapsedChange: vi.fn(),
    newResult: false,
    width: 360,
    pricing: <button type="button">Calculate</button>,
    service: <ServiceForm />,
    ...overrides,
  };
  const utils = render(
    <TooltipProvider>
      <InspectorPanel {...props} />
    </TooltipProvider>,
  );
  return { ...utils, onAction, props };
}

/** Wires `onAction` through `nextArrangement`, as WorkspacePage does. */
function Stateful({
  initial = DEFAULT_ARRANGEMENT,
  onAction,
}: {
  initial?: InspectorArrangement;
  onAction?: (a: InspectorAction) => void;
}) {
  const [arrangement, setArrangement] = useState(initial);
  const [collapsed, setCollapsed] = useState(false);
  return (
    <TooltipProvider>
      <InspectorPanel
        arrangement={arrangement}
        onAction={(a) => {
          onAction?.(a);
          setArrangement((cur) => nextArrangement(cur, a));
        }}
        collapsed={collapsed}
        onCollapsedChange={setCollapsed}
        newResult={false}
        width={360}
        pricing={<button type="button">Calculate</button>}
        service={<ServiceForm />}
      />
    </TooltipProvider>
  );
}

const split = (upper: "pricing" | "service" = "pricing"): InspectorArrangement => ({
  mode: "split",
  upper,
  front: "pricing",
  split: 0.5,
});

describe("InspectorPanel merged (US2)", () => {
  it("is the Inspector landmark with Pricing and Service tabs", () => {
    renderPanel();
    const inspector = screen.getByRole("complementary", { name: "Inspector" });
    const tablist = within(inspector).getByRole("tablist", { name: "Inspector tabs" });
    expect(
      within(tablist)
        .getAllByRole("tab")
        .map((t) => t.textContent),
    ).toEqual(["Pricing", "Service"]);
    expect(within(tablist).getByRole("tab", { name: "Pricing" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("shows only the front tab's body", () => {
    renderPanel({ arrangement: { ...DEFAULT_ARRANGEMENT, front: "service" } });
    expect(screen.getByRole("tabpanel", { name: "Service" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Calculate" })).toBeNull();
    expect(screen.getByLabelText("vCPUs")).toBeVisible();
  });

  it("switches tabs by click and by arrow key", () => {
    const { onAction } = renderPanel();
    fireEvent.click(screen.getByRole("tab", { name: "Service" }));
    expect(onAction).toHaveBeenLastCalledWith({ type: "select-tab", tab: "service" });
    fireEvent.keyDown(screen.getByRole("tab", { name: "Pricing" }), { key: "ArrowRight" });
    expect(onAction).toHaveBeenLastCalledWith({ type: "select-tab", tab: "service" });
  });

  it("keeps unsaved Service input when Pricing comes to the front", () => {
    render(<Stateful initial={{ ...DEFAULT_ARRANGEMENT, front: "service" }} />);
    fireEvent.change(screen.getByLabelText("vCPUs"), { target: { value: "8" } });
    fireEvent.click(screen.getByRole("tab", { name: "Pricing" }));
    // Hidden, but still mounted.
    expect(screen.getByLabelText("vCPUs")).not.toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "Service" }));
    expect(screen.getByLabelText("vCPUs")).toHaveValue("8");
  });

  it("collapses to a rail and expands again", () => {
    const onCollapsedChange = vi.fn();
    renderPanel({ onCollapsedChange });
    fireEvent.click(screen.getByRole("button", { name: "Collapse inspector" }));
    expect(onCollapsedChange).toHaveBeenCalledWith(true);
  });

  it("offers Pricing and Service on the rail, each expanding to its tab", () => {
    const onCollapsedChange = vi.fn();
    const { onAction } = renderPanel({ collapsed: true, onCollapsedChange });
    expect(screen.getByRole("button", { name: "Expand inspector" })).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Service" }));
    expect(onAction).toHaveBeenCalledWith({ type: "select-tab", tab: "service" });
    expect(onCollapsedChange).toHaveBeenCalledWith(false);
  });

  it("marks the rail's Pricing button when a new result is waiting", () => {
    renderPanel({ collapsed: true, newResult: true });
    expect(screen.getByRole("button", { name: "Pricing — new result" })).toBeInTheDocument();
  });

  it("keeps unsaved Service input across collapsing", () => {
    render(<Stateful initial={{ ...DEFAULT_ARRANGEMENT, front: "service" }} />);
    fireEvent.change(screen.getByLabelText("vCPUs"), { target: { value: "16" } });
    fireEvent.click(screen.getByRole("button", { name: "Collapse inspector" }));
    fireEvent.click(screen.getByRole("button", { name: "Expand inspector" }));
    expect(screen.getByLabelText("vCPUs")).toHaveValue("16");
  });
});

/** Radix DropdownMenu opens on pointerdown (jsdom has no PointerEvent) or on Enter. */
async function openOptions(name: string) {
  const trigger = screen.getByRole("button", { name });
  await act(async () => {
    fireEvent.keyDown(trigger, { key: "Enter" });
  });
  return screen.findByRole("menu");
}

describe("InspectorPanel split (US3)", () => {
  it("shows two panes, one tab each", () => {
    renderPanel({ arrangement: split("service") });
    const upper = screen.getByRole("tablist", { name: "Upper inspector pane" });
    const lower = screen.getByRole("tablist", { name: "Lower inspector pane" });
    expect(within(upper).getByRole("tab").textContent).toBe("Service");
    expect(within(lower).getByRole("tab").textContent).toBe("Pricing");
    expect(screen.getByRole("button", { name: "Calculate" })).toBeVisible();
    expect(screen.getByLabelText("vCPUs")).toBeVisible();
  });

  it("offers Move to lower half when merged, and does it", async () => {
    const { onAction } = renderPanel();
    const menu = await openOptions("Pricing tab options");
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((m) => m.textContent),
    ).toEqual(["Move to lower half"]);
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Move to lower half" }));
    expect(onAction).toHaveBeenCalledWith({ type: "drop-on-lower", tab: "pricing" });
  });

  it("offers Merge and Swap when split", async () => {
    const { onAction } = renderPanel({ arrangement: split("pricing") });
    let menu = await openOptions("Service tab options");
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((m) => m.textContent),
    ).toEqual(["Merge", "Swap"]);
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Merge" }));
    expect(onAction).toHaveBeenCalledWith({ type: "merge", tab: "service" });
    menu = await openOptions("Pricing tab options");
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Swap" }));
    expect(onAction).toHaveBeenCalledWith({ type: "swap" });
  });

  it("exposes the divider's position and moves it 5% per arrow key", () => {
    const { onAction } = renderPanel({ arrangement: split() });
    const divider = screen.getByRole("separator", { name: "Resize inspector panes" });
    expect(divider).toHaveAttribute("aria-valuenow", "50");
    expect(divider).toHaveAttribute("aria-valuemin", "20");
    expect(divider).toHaveAttribute("aria-valuemax", "80");
    fireEvent.keyDown(divider, { key: "ArrowDown" });
    expect(onAction).toHaveBeenLastCalledWith({ type: "set-split", split: 0.55 });
    fireEvent.keyDown(divider, { key: "ArrowUp" });
    expect(onAction).toHaveBeenLastCalledWith({ type: "set-split", split: 0.45 });
  });

  it("keeps unsaved Service input across split, swap and merge", async () => {
    render(<Stateful initial={{ ...DEFAULT_ARRANGEMENT, front: "service" }} />);
    fireEvent.change(screen.getByLabelText("vCPUs"), { target: { value: "4" } });
    let menu = await openOptions("Service tab options");
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Move to lower half" }));
    expect(screen.getByRole("tablist", { name: "Lower inspector pane" })).toBeInTheDocument();
    menu = await openOptions("Service tab options");
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Swap" }));
    menu = await openOptions("Pricing tab options");
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Merge" }));
    expect(screen.getByRole("tablist", { name: "Inspector tabs" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Service" }));
    expect(screen.getByLabelText("vCPUs")).toHaveValue("4");
  });
});

/** jsdom has no layout: give the inspector and its upper tab bar real-looking boxes. */
function fakeLayout() {
  const inspector = screen.getByRole("complementary", { name: "Inspector" });
  const container = inspector.firstElementChild as HTMLElement;
  const bar = screen.getAllByRole("tablist")[0].parentElement as HTMLElement;
  const rect = (top: number, height: number) =>
    ({
      top,
      bottom: top + height,
      height,
      left: 0,
      right: 360,
      width: 360,
      x: 0,
      y: top,
    }) as DOMRect;
  container.getBoundingClientRect = () => rect(0, 800);
  bar.getBoundingClientRect = () => rect(0, 36);
}

function pointer(type: string, target: EventTarget, x: number, y: number) {
  const event = new MouseEvent(type, { bubbles: true, clientX: x, clientY: y, button: 0 });
  Object.defineProperty(event, "pointerId", { value: 1 });
  target.dispatchEvent(event);
}

describe("InspectorPanel tab dragging (US3)", () => {
  it("dropping a tab on the lower half splits with it below", () => {
    const { onAction } = renderPanel();
    fakeLayout();
    const tab = screen.getByRole("tab", { name: "Service" });
    act(() => pointer("pointerdown", tab, 100, 10));
    act(() => pointer("pointermove", window, 100, 300));
    act(() => pointer("pointermove", window, 100, 600));
    expect(screen.getByText("Drop to split")).toBeInTheDocument();
    act(() => pointer("pointerup", window, 100, 600));
    expect(onAction).toHaveBeenCalledWith({ type: "drop-on-lower", tab: "service" });
    expect(screen.queryByText("Drop to split")).toBeNull();
  });

  it("dropping the lower tab on the upper bar merges", () => {
    const { onAction } = renderPanel({ arrangement: split("pricing") });
    fakeLayout();
    const tab = within(screen.getByRole("tablist", { name: "Lower inspector pane" })).getByRole(
      "tab",
    );
    act(() => pointer("pointerdown", tab, 100, 500));
    act(() => pointer("pointermove", window, 100, 20));
    act(() => pointer("pointerup", window, 100, 20));
    expect(onAction).toHaveBeenCalledWith({ type: "drop-on-upper-bar", tab: "service" });
  });

  it("a drop outside both zones, or Escape, changes nothing", () => {
    const { onAction } = renderPanel();
    fakeLayout();
    const tab = screen.getByRole("tab", { name: "Service" });
    act(() => pointer("pointerdown", tab, 100, 10));
    act(() => pointer("pointermove", window, 100, 200)); // upper half, below the bar
    act(() => pointer("pointerup", window, 100, 200));
    act(() => pointer("pointerdown", tab, 100, 10));
    act(() => pointer("pointermove", window, 100, 600));
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    act(() => pointer("pointerup", window, 100, 600));
    expect(onAction).not.toHaveBeenCalled();
  });

  it("a click without movement only selects the tab", () => {
    const { onAction } = renderPanel();
    fakeLayout();
    const tab = screen.getByRole("tab", { name: "Service" });
    act(() => pointer("pointerdown", tab, 100, 10));
    act(() => pointer("pointermove", window, 102, 11));
    act(() => pointer("pointerup", window, 102, 11));
    fireEvent.click(tab);
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onAction).toHaveBeenCalledWith({ type: "select-tab", tab: "service" });
  });
});
