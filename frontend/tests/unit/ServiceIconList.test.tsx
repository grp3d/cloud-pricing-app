import { ReactFlowProvider } from "@xyflow/react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { SKUSelection } from "../../src/api/client";
import { ServiceList } from "../../src/components/workspace/ArchitectureDiagramPanel";
import { buildServicePopupLines } from "../../src/lib/servicePopup";
import { TooltipProvider } from "../../src/components/ui/tooltip";

function selection(overrides: Partial<SKUSelection> = {}): SKUSelection {
  return {
    id: "sel-1",
    service_code: "AmazonDynamoDB",
    sku: "3ERQSZWPAMX2JWHN",
    pricing_term: "on_demand",
    purchase_option: "not_applicable",
    usage_quantity: "1",
    unit: "ReadRequestUnits",
    attributes: {
      groupDescription: "DynamoDB PayPerRequest Read Request Units",
      usagetype: "EU-ReadRequestUnits",
      operation: "PayPerRequestThroughput",
    },
    product_family: "Amazon DynamoDB PayPerRequest Throughput",
    ...overrides,
  };
}

/** ServiceList reads the live canvas zoom (US3), so every render sits inside the providers the
 * real canvas supplies. */
function wrap(children: ReactNode) {
  return (
    <ReactFlowProvider>
      <TooltipProvider>{children}</TooltipProvider>
    </ReactFlowProvider>
  );
}

describe("ServiceList (canvas service icons)", () => {
  it("renders one icon button per SKU selection, repeating the same icon for the same service", () => {
    render(
      wrap(
        <ServiceList
          innerWidth={360}
          skuSelections={[selection({ id: "a" }), selection({ id: "b", sku: "OTHERSKU00000000" })]}
          onSelectService={vi.fn()}
        />,
      ),
    );
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(2);
    const [first, second] = buttons.map((b) => b.querySelector("img")?.getAttribute("src"));
    expect(first).toContain("Amazon-DynamoDB");
    expect(second).toBe(first);
  });

  it("no longer renders the old 'service_code / sku' text rows", () => {
    const { container } = render(
      wrap(
        <ServiceList innerWidth={360} skuSelections={[selection()]} onSelectService={vi.fn()} />,
      ),
    );
    expect(container.textContent ?? "").not.toMatch(/ \/ /);
  });

  it("selects the clicked service", () => {
    const onSelectService = vi.fn();
    render(
      wrap(
        <ServiceList
          innerWidth={360}
          skuSelections={[selection()]}
          onSelectService={onSelectService}
        />,
      ),
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onSelectService).toHaveBeenCalledWith("sel-1");
  });

  it("marks only the selected service as pressed", () => {
    render(
      wrap(
        <ServiceList
          innerWidth={360}
          skuSelections={[selection({ id: "a" }), selection({ id: "b" })]}
          selectedServiceId="b"
          onSelectService={vi.fn()}
        />,
      ),
    );
    const [a, b] = screen.getAllByRole("button");
    expect(a).toHaveAttribute("aria-pressed", "false");
    expect(b).toHaveAttribute("aria-pressed", "true");
  });

  it("shows the empty message unless hideEmptyMessage", () => {
    const { rerender } = render(
      wrap(<ServiceList innerWidth={360} skuSelections={[]} onSelectService={vi.fn()} />),
    );
    expect(screen.getByText("No services yet.")).toBeInTheDocument();
    rerender(
      wrap(
        <ServiceList
          innerWidth={360}
          skuSelections={[]}
          onSelectService={vi.fn()}
          hideEmptyMessage
        />,
      ),
    );
    expect(screen.queryByText("No services yet.")).not.toBeInTheDocument();
  });

  it("names each icon with its pop-up content (FR-012)", () => {
    render(
      wrap(
        <ServiceList innerWidth={360} skuSelections={[selection()]} onSelectService={vi.fn()} />,
      ),
    );
    expect(
      screen.getByRole("button", { name: buildServicePopupLines(selection()).join(", ") }),
    ).toBeInTheDocument();
  });

  // Opening the Radix tooltip in jsdom takes ~5s (it did before 016 too), right at Vitest's
  // default 5s limit — this test gets a longer timeout rather than failing intermittently.
  it("shows the labeled pop-up lines, each on its own line, when the icon is focused", async () => {
    const { container } = render(
      wrap(
        <ServiceList innerWidth={360} skuSelections={[selection()]} onSelectService={vi.fn()} />,
      ),
    );
    await act(async () => {
      fireEvent.focus(container.querySelector("button") as HTMLButtonElement);
    });
    const skuLine = (await screen.findAllByText("Sku: 3ERQSZWPAMX2JWHN"))[0];
    const usageLine = screen.getAllByText("UsageType: EU-ReadRequestUnits")[0];
    expect(skuLine).not.toBe(usageLine);
    expect(skuLine.parentElement).toBe(usageLine.parentElement);
  }, 15_000);

  // 016-canvas-icon-layout, FR-001/FR-002: 60px icons, up to 3 per row, 120 apart.
  it("renders 60px icons at their default positions, 3 per row", () => {
    const selections = ["a", "b", "c", "d"].map((id) => selection({ id }));
    const { container } = render(
      wrap(<ServiceList innerWidth={360} skuSelections={selections} onSelectService={vi.fn()} />),
    );
    const buttons = screen.getAllByRole("button");
    expect(buttons[0].className).toContain("size-[60px]");
    expect(buttons[2]).toHaveStyle({ left: "240px", top: "0px" });
    expect(buttons[3]).toHaveStyle({ left: "0px", top: "120px" });
    const area = container.querySelector("div.relative") as HTMLElement;
    expect(area).toHaveStyle({ height: `${120 + 60 + 16}px` });
  });

  it("honors hand-placed positions", () => {
    render(
      wrap(
        <ServiceList
          innerWidth={360}
          skuSelections={[selection({ id: "a" })]}
          savedPositions={{ a: { x: 200, y: 30 } }}
          onSelectService={vi.fn()}
        />,
      ),
    );
    expect(screen.getByRole("button")).toHaveStyle({ left: "200px", top: "30px" });
  });
});
