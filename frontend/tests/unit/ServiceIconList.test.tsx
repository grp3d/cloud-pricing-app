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
  });

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

// --- 020 (T024): GCP and Azure icons and the fallback tile -----------------------------------

describe("ServiceList provider icons (020)", () => {
  const gcpMachine = selection({
    id: "gcp-1",
    service_code: "6F81-5844-456A",
    sku: "BB77-5FDA-69D9",
    product_family: "Compute > GCE > VMs On Demand",
    attributes: {},
    service_name: "Compute Engine",
  });
  const gcpMarketplace = selection({
    id: "gcp-2",
    service_code: "0017-8C5E-5B91",
    sku: "MKT-SKU",
    product_family: "Marketplace Services > OpenLogic",
    attributes: {},
    service_name:
      "OpenLogic CentOS 7.8 (v20200922) - Security Hardened with a very long marketplace name",
  });

  function srcs() {
    return screen.getAllByRole("button").map((b) => b.querySelector("img")?.getAttribute("src"));
  }

  it("renders a mapped GCP service's own icon", () => {
    render(
      wrap(
        <ServiceList
          innerWidth={360}
          skuSelections={[gcpMachine]}
          onSelectService={vi.fn()}
          provider="gcp"
        />,
      ),
    );
    const [src] = srcs();
    expect(src).toContain("Compute-Engine");
    expect(src).not.toMatch(/aws-icons/);
    expect(screen.queryByTestId("fallback-service-name")).toBeNull();
  });

  it("renders the fallback tile with the provider logo and the name, keeping the full name accessible", () => {
    render(
      wrap(
        <ServiceList
          innerWidth={360}
          skuSelections={[gcpMarketplace]}
          onSelectService={vi.fn()}
          provider="gcp"
        />,
      ),
    );
    const [src] = srcs();
    expect(src).toContain("gcp_icon");
    const name = screen.getByTestId("fallback-service-name");
    expect(name.textContent).toBe(gcpMarketplace.service_name);
    expect(name).toHaveClass("line-clamp-3", "break-words", "text-foreground");
    const button = screen.getByRole("button");
    expect(button.querySelector(".size-\\[60px\\]")).not.toBeNull();
    // FR-009: the full name first (the tile cuts it), then the usual lines. 021 US7: those
    // lines now start with the name themselves, so it isn't repeated.
    const lines = buildServicePopupLines(gcpMarketplace);
    expect(lines[0]).toBe(gcpMarketplace.service_name);
    expect(button).toHaveAccessibleName(lines.join(", "));
  });

  it("gives each fallback tile its own name", () => {
    render(
      wrap(
        <ServiceList
          innerWidth={360}
          skuSelections={[
            gcpMarketplace,
            { ...gcpMarketplace, id: "gcp-3", service_name: "Another Product" },
          ]}
          onSelectService={vi.fn()}
          provider="gcp"
        />,
      ),
    );
    expect(screen.getAllByTestId("fallback-service-name").map((n) => n.textContent)).toEqual([
      gcpMarketplace.service_name,
      "Another Product",
    ]);
  });

  it("renders Azure managed disks with the Disks icon, not the VM's", () => {
    render(
      wrap(
        <ServiceList
          innerWidth={360}
          skuSelections={[
            selection({
              id: "vm",
              service_code: "DZH313Z7MMC8",
              product_family: "Virtual Machines Dsv5 Series",
            }),
            selection({
              id: "disk",
              service_code: "DZH317F1HKN0",
              product_family: "Premium SSD Managed Disks",
            }),
          ]}
          onSelectService={vi.fn()}
          provider="azure"
        />,
      ),
    );
    const [vm, disk] = srcs();
    expect(vm).toContain("Virtual-Machine");
    expect(disk).toContain("Disks");
  });

  it("renders AWS exactly as before when no provider is given, or aws", () => {
    const { container: before } = render(
      wrap(
        <ServiceList innerWidth={360} skuSelections={[selection()]} onSelectService={vi.fn()} />,
      ),
    );
    const { container: aws } = render(
      wrap(
        <ServiceList
          innerWidth={360}
          skuSelections={[selection()]}
          onSelectService={vi.fn()}
          provider="aws"
        />,
      ),
    );
    expect(aws.innerHTML).toBe(before.innerHTML);
    expect(aws.querySelector("img")?.getAttribute("src")).toContain("Amazon-DynamoDB");
  });

  it("keeps icon positions the same for every provider (FR-013)", () => {
    const positions = (provider: "aws" | "gcp" | "azure") => {
      const { container, unmount } = render(
        wrap(
          <ServiceList
            innerWidth={360}
            skuSelections={[
              { ...gcpMachine, id: "a" },
              { ...gcpMarketplace, id: "b" },
              { ...gcpMachine, id: "c" },
              { ...gcpMarketplace, id: "d" },
            ]}
            savedPositions={{ c: { x: 120, y: 60 } }}
            onSelectService={vi.fn()}
            provider={provider}
          />,
        ),
      );
      const result = Array.from(container.querySelectorAll("button")).map(
        (b) => `${b.style.left},${b.style.top}`,
      );
      unmount();
      return result;
    };
    const aws = positions("aws");
    expect(positions("gcp")).toEqual(aws);
    expect(positions("azure")).toEqual(aws);
  });
});
