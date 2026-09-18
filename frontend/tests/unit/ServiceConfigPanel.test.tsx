import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SKUSelection } from "../../src/api/client";
import {
  ServiceConfigPanel,
  type ServiceConfigPanelProps,
} from "../../src/components/workspace/ServiceConfigPanel";
import { TooltipProvider } from "../../src/components/ui/tooltip";
import { existingServiceSelection } from "../../src/lib/serviceConfigSelection";

function panel(props: ServiceConfigPanelProps) {
  return (
    <TooltipProvider>
      <ServiceConfigPanel {...props} />
    </TooltipProvider>
  );
}

function sku(overrides: Partial<SKUSelection>): SKUSelection {
  return {
    id: "sku-a",
    service_code: "AmazonEC2",
    sku: "SKU-A",
    pricing_term: "on_demand",
    purchase_option: "not_applicable",
    usage_quantity: "100",
    unit: "Hrs",
    attributes: {},
    ...overrides,
  };
}

const noop = {
  onSubmitNew: vi.fn(),
  onSubmitExisting: vi.fn(),
  onRemoveExisting: vi.fn(),
  actionError: null,
  onDismissActionError: vi.fn(),
  width: 280,
};

// Live user report (regression): editing one service's usage quantity was landing on a
// *different* service instead of the one actually selected in the UI. Root cause was
// PricingInputsForm's internal `useState` never resetting when ServiceConfigPanel re-rendered
// with a different selected service (same component instance reused, so React never re-ran its
// initializers) -- fixed by keying PricingInputsForm on the selected service's own identity.
describe("ServiceConfigPanel — switching the selected service", () => {
  it("shows the newly-selected service's own usage quantity, not the previous one's", () => {
    const skuA = sku({ id: "sku-a", usage_quantity: "100" });
    const skuB = sku({ id: "sku-b", sku: "SKU-B", usage_quantity: "200" });

    const { rerender } = render(
      panel({ ...noop, selection: existingServiceSelection("sku-a"), resolvedExisting: skuA }),
    );
    expect(screen.getByLabelText(/Usage quantity/)).toHaveValue(100);

    rerender(
      panel({ ...noop, selection: existingServiceSelection("sku-b"), resolvedExisting: skuB }),
    );
    expect(screen.getByLabelText(/Usage quantity/)).toHaveValue(200);
  });

  it("shows the newly-selected service's own term/purchase option too, not the previous one's", () => {
    const skuA = sku({ id: "sku-a", pricing_term: "on_demand", purchase_option: "not_applicable" });
    const skuB = sku({
      id: "sku-b",
      sku: "SKU-B",
      pricing_term: "reserved_1yr",
      purchase_option: "all_upfront",
    });

    const { rerender } = render(
      panel({ ...noop, selection: existingServiceSelection("sku-a"), resolvedExisting: skuA }),
    );
    expect(screen.getByLabelText("Term")).toHaveValue("on_demand");

    rerender(
      panel({ ...noop, selection: existingServiceSelection("sku-b"), resolvedExisting: skuB }),
    );
    expect(screen.getByLabelText("Term")).toHaveValue("reserved_1yr");
    expect(screen.getByLabelText("Purchase option")).toHaveValue("all_upfront");
  });

  it("still shows the same service's own value across an unrelated re-render (no stale reset)", () => {
    const skuA = sku({ id: "sku-a", usage_quantity: "100" });

    const { rerender } = render(
      panel({ ...noop, selection: existingServiceSelection("sku-a"), resolvedExisting: skuA }),
    );
    expect(screen.getByLabelText(/Usage quantity/)).toHaveValue(100);

    // Same service, only an unrelated prop (actionError) changes -- the form must not remount
    // (and so must not discard whatever the user may have already typed) just because *some*
    // prop on the panel changed.
    rerender(
      panel({
        ...noop,
        selection: existingServiceSelection("sku-a"),
        resolvedExisting: skuA,
        actionError: "unrelated error",
      }),
    );
    expect(screen.getByLabelText(/Usage quantity/)).toHaveValue(100);
  });
});
