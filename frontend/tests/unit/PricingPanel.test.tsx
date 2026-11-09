import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CalculationResult } from "../../src/api/client";
import { PricingPanel, type PricingPanelProps } from "../../src/components/workspace/PricingPanel";
import { TooltipProvider } from "../../src/components/ui/tooltip";
import { serviceLabel } from "../../src/lib/serviceLabel";

const calculation: CalculationResult = {
  snapshot_date: "2026-09-24",
  snapshot_revision: 1,
  duration: "1_month",
  total_price: "12.00",
  currency: "USD",
  line_items: [
    {
      sku_selection_id: "sel-1",
      service_code: "AmazonEC2",
      sku: "SKU1",
      price: "12.00",
      priceable: true,
      region: "us-east-1",
    },
  ],
  unpriceable: [],
  warnings: [],
};

function renderPanel(overrides: Partial<PricingPanelProps> = {}) {
  const props: PricingPanelProps = {
    duration: "1_month",
    onDurationChange: vi.fn(),
    onCalculate: vi.fn(),
    isCalculating: false,
    calculation,
    calculationError: null,
    onRetry: vi.fn(),
    priceChange: null,
    skuAttributesById: new Map(),
    isOutOfDate: false,
    ...overrides,
  };
  return render(
    <TooltipProvider>
      <PricingPanel {...props} />
    </TooltipProvider>,
  );
}

const NOTICE = "Architecture has been updated since last pricing";

describe("PricingPanel snapshot label (018, FR-059)", () => {
  it("shows only the date for a snapshot's first revision", () => {
    renderPanel();
    const timestamp = screen.getByText("Data Timestamp: 2026-09-24");
    expect(timestamp.textContent).toBe("Data Timestamp: 2026-09-24");
  });

  it("shows a later revision in parentheses, in a lighter shade", () => {
    renderPanel({ calculation: { ...calculation, snapshot_revision: 2 } });
    const revision = screen.getByText("(r2)");
    expect(revision.parentElement?.textContent).toBe("Data Timestamp: 2026-09-24 (r2)");
    expect(revision).toHaveClass("opacity-60");
  });
});

describe("PricingPanel out-of-date notice (015, FR-018a)", () => {
  it("shows the notice directly below the Data Timestamp line", () => {
    renderPanel({ isOutOfDate: true });
    const timestamp = screen.getByText("Data Timestamp: 2026-09-24");
    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent(NOTICE);
    expect(timestamp.nextElementSibling).toBe(notice);
  });

  it("hides the notice when the stored result is current", () => {
    renderPanel({ isOutOfDate: false });
    expect(screen.queryByText(NOTICE)).not.toBeInTheDocument();
  });
});

describe("PricingPanel word-wrap toggle placement (015, FR-023)", () => {
  it("sits on the Price per Sku heading row, not after Data Timestamp", () => {
    renderPanel();
    const toggle = screen.getByRole("button", { name: "Enable word wrap for Price per Sku" });
    const heading = screen.getByRole("heading", { name: "Price per Sku" });
    expect(toggle.parentElement).toBe(heading.parentElement);

    const timestamp = screen.getByText("Data Timestamp: 2026-09-24");
    expect(timestamp.nextElementSibling).toBeNull();
  });

  it("still toggles word wrap", () => {
    renderPanel();
    const toggle = screen.getByRole("button", { name: "Enable word wrap for Price per Sku" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(
      screen.getByRole("button", { name: "Disable word wrap for Price per Sku" }),
    ).toHaveAttribute("aria-pressed", "true");
  });
});

// --- 019 (T057, contracts §5): line detail -----------------------------------------------------

describe("PricingPanel line detail (019)", () => {
  it("shows the tier breakdown and a GCP machine's components", () => {
    renderPanel({
      calculation: {
        ...calculation,
        snapshot_date: "2026-11-02",
        total_price: "189.52",
        line_items: [
          {
            sku_selection_id: "egress",
            service_code: "6F81-5844-456A",
            sku: "F274-1692-F213",
            price: "45.24",
            priceable: true,
            region: "us-east1",
            price_type_label: "On demand",
            tiers: [
              { from_quantity: "0", to_quantity: "100", rate: "0", quantity: "100", cost: "0" },
              {
                from_quantity: "100",
                to_quantity: null,
                rate: "0.087",
                quantity: "520",
                cost: "45.24",
              },
            ],
          },
          {
            sku_selection_id: "machine",
            service_code: "6F81-5844-456A",
            sku: "BB77-5FDA-69D9",
            price: "144.28",
            priceable: true,
            region: "us-east1",
            price_type_label: "Committed use, 1 year",
            components: [
              { label: "vCPUs", sku: "BB77", quantity: "2976", rate: "0.031611", cost: "94.07" },
              {
                label: "Memory (GiB)",
                sku: "5B01",
                quantity: "11904",
                rate: "0.004237",
                cost: "50.21",
              },
            ],
          },
        ],
      },
    });
    const tiers = screen.getByRole("list", { name: "Price tiers" });
    expect(tiers.textContent).toContain("100–∞ at 0.087: 520");
    expect(tiers.textContent).toContain("45.24");
    const components = screen.getByRole("list", { name: "Price components" });
    expect(components.textContent).toContain("vCPUs: 2,976 at 0.031611");
    expect(components.textContent).toContain("Memory (GiB): 11,904 at 0.004237");
    expect(screen.getByText("Committed use, 1 year")).toBeInTheDocument();
    // An on-demand line doesn't repeat its price type.
    expect(screen.queryByText("On demand")).toBeNull();
  });

  it("adds nothing to a plain on-demand line", () => {
    renderPanel();
    expect(screen.queryByRole("list", { name: "Price tiers" })).toBeNull();
    expect(screen.queryByRole("list", { name: "Price components" })).toBeNull();
  });
});

describe("PricingPanel Price Change not available (020, FR-005)", () => {
  const NOTE = "Not available: previous calculation from prior version is unreliable";

  it("shows the note in muted text instead of a figure", () => {
    renderPanel({ priceChange: null, priceChangeUnavailable: true });
    const note = screen.getByText(NOTE);
    expect(note).toHaveClass("text-muted-foreground");
    expect(screen.queryByText(/Price Change: [+-]?\$/)).toBeNull();
  });

  it("sits where the Price Change line goes, right below the total", () => {
    renderPanel({ priceChangeUnavailable: true });
    const total = screen.getByText(/^Total:/);
    expect(total.nextElementSibling).toBe(screen.getByText(NOTE));
  });

  it("shows no note otherwise", () => {
    renderPanel({ priceChange: "5" });
    expect(screen.queryByText(NOTE)).toBeNull();
    expect(screen.getByText(/Price Change:/)).toBeInTheDocument();
  });
});

describe("Calculate button colour (021 US5, FR-040)", () => {
  const button = () => screen.getByRole("button", { name: "Calculate" });

  it("is dark blue when the price is out of date", () => {
    renderPanel({ isOutOfDate: true });
    expect(button()).toHaveAttribute("data-variant", "default");
  });

  it("is dark blue when nothing has been priced yet", () => {
    renderPanel({ calculation: null });
    expect(button()).toHaveAttribute("data-variant", "default");
  });

  it("is light blue when the price is current, and still calculates", () => {
    const onCalculate = vi.fn();
    renderPanel({ onCalculate });
    expect(button()).toHaveAttribute("data-variant", "soft");
    fireEvent.click(button());
    expect(onCalculate).toHaveBeenCalledTimes(1);
  });
});

describe("Price per Sku names (021 US7, FR-047)", () => {
  it("shows a readable name and description, with the codes muted", () => {
    renderPanel({
      skuLabelsById: new Map([
        [
          "sel-1",
          serviceLabel({
            service_code: "95FF-2EF5-5EA1",
            sku: "EE2C-E844-D760",
            service_name: "Cloud Storage",
            summary: "Nearline Class A Operations",
          }),
        ],
      ]),
    });
    expect(screen.getByText("Cloud Storage — Nearline Class A Operations")).toHaveAttribute(
      "title",
      "Cloud Storage — Nearline Class A Operations",
    );
    expect(screen.getByText("95FF-2EF5-5EA1 / EE2C-E844-D760")).toHaveClass(
      "text-muted-foreground",
    );
  });

  it("keeps service_code / sku for AWS", () => {
    renderPanel({
      skuLabelsById: new Map([["sel-1", serviceLabel({ service_code: "AmazonEC2", sku: "SKU1" })]]),
    });
    expect(screen.getByText("AmazonEC2 / SKU1")).toBeInTheDocument();
  });
});

describe("PricingPanel pinned summary (021 US8, FR-048)", () => {
  it("pins duration, Calculate, the total and Price Change above a divider; the rest scrolls", () => {
    renderPanel({ priceChange: "1.50" });
    const pinned = screen.getByTestId("pricing-pinned");
    const scroll = screen.getByTestId("pricing-scroll");
    expect(within(pinned).getByLabelText("Duration")).toBeInTheDocument();
    expect(within(pinned).getByRole("button", { name: "Calculate" })).toBeInTheDocument();
    expect(within(pinned).getByRole("heading", { name: /^Total:/ })).toBeInTheDocument();
    expect(within(pinned).getByText(/^Price Change:/)).toBeInTheDocument();
    expect(pinned.lastElementChild).toHaveAttribute("data-slot", "separator");
    expect(within(scroll).getByRole("region", { name: "Price per Sku" })).toBeInTheDocument();
    expect(within(scroll).getByText(/^Data Timestamp:/)).toBeInTheDocument();
    expect(scroll).toHaveClass("overflow-auto");
    // The result region still holds the total, for the existing checks.
    expect(
      within(screen.getByRole("region", { name: "Calculation result" })).getByRole("heading", {
        name: /^Total:/,
      }),
    ).toBeInTheDocument();
  });

  it("keeps the divider under the controls before anything is priced", () => {
    renderPanel({ calculation: null });
    expect(screen.getByTestId("pricing-pinned").lastElementChild).toHaveAttribute(
      "data-slot",
      "separator",
    );
    expect(screen.queryByRole("region", { name: "Calculation result" })).toBeNull();
  });
});
