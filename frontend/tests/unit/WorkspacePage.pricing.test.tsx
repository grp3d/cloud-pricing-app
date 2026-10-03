import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, type ArchitectureDetail, type CalculationResult } from "../../src/api/client";
import { TooltipProvider } from "../../src/components/ui/tooltip";
import { writePricingResult } from "../../src/lib/architecturePricingResults";
import { WorkspacePage } from "../../src/pages/WorkspacePage";

const ARCH_ID = "arch-a";

const selection = {
  id: "sel-1",
  service_code: "AmazonEC2",
  sku: "SKU1",
  pricing_term: "on_demand" as const,
  purchase_option: "not_applicable" as const,
  usage_quantity: "730",
  unit: "Hrs",
  attributes: {},
  product_family: "Compute Instance",
};

const architecture = {
  id: ARCH_ID,
  name: "A",
  provider: "aws",
  collections: [
    {
      id: "coll-1",
      type: "application_component",
      name: "Web",
      region: "us-east-1",
      parent_collection_id: null,
      sku_selections: [selection],
    },
  ],
  connectors: [],
} as unknown as ArchitectureDetail;

function result(total: string): CalculationResult {
  return {
    snapshot_date: "2026-09-24",
    snapshot_revision: 1,
    duration: "1_year",
    total_price: total,
    currency: "USD",
    line_items: [],
    unpriceable: [],
    warnings: [],
  };
}

function renderWorkspace() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[`/architectures/${ARCH_ID}`]}>
          <Routes>
            <Route path="/architectures/:architectureId" element={<WorkspacePage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

describe("WorkspacePage per-architecture pricing (015, US4)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.spyOn(api, "listProviders").mockResolvedValue([]);
    vi.spyOn(api, "listRegions").mockResolvedValue([]);
    vi.spyOn(api, "listArchitectures").mockResolvedValue([]);
    vi.spyOn(api, "getCurrentUser").mockResolvedValue(
      null as unknown as Awaited<ReturnType<typeof api.getCurrentUser>>,
    );
    vi.spyOn(api, "getArchitecture").mockResolvedValue(architecture);
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows a stored result without calculating, at its stored Duration (FR-018, FR-018b, SC-006)", async () => {
    const calculate = vi.spyOn(api, "calculate");
    writePricingResult(ARCH_ID, {
      version: 1,
      result: result("123.45"),
      duration: "1_year",
      priceChange: null,
      pricedContents: [
        {
          service_code: "AmazonEC2",
          sku: "SKU1",
          pricing_term: "on_demand",
          purchase_option: "not_applicable",
          usage_quantity: "730",
          region: "us-east-1",
        },
      ],
      calculatedAt: "2026-09-25T00:00:00.000Z",
    });

    renderWorkspace();

    expect(await screen.findByText(/Total: .*123\.45/)).toBeInTheDocument();
    expect(screen.getByLabelText("Duration")).toHaveValue("1_year");
    expect(screen.queryByText("Architecture has been updated since last pricing")).toBeNull();
    expect(calculate).not.toHaveBeenCalled();
  });

  it("calculates automatically when the architecture has no stored result (FR-017)", async () => {
    const calculate = vi.spyOn(api, "calculate").mockResolvedValue(result("7.00"));

    renderWorkspace();

    expect(await screen.findByText(/Total: .*7\.00/)).toBeInTheDocument();
    expect(calculate).toHaveBeenCalledTimes(1);
    expect(calculate).toHaveBeenCalledWith(ARCH_ID, "1_month");
  });
});
