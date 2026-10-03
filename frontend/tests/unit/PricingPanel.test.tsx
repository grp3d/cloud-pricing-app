import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CalculationResult } from "../../src/api/client";
import { PricingPanel, type PricingPanelProps } from "../../src/components/workspace/PricingPanel";
import { TooltipProvider } from "../../src/components/ui/tooltip";

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
    width: 320,
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
