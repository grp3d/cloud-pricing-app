import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
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

// --- 020 (T013, User Story 1) ----------------------------------------------------------------

describe("WorkspacePage Price Change with provider options (020)", () => {
  const options = (vcpus: number) => ({
    kind: "gcp_machine" as const,
    version: 1 as const,
    vcpus,
    memory_gib: "16",
    ram_sku: "RAM",
  });
  const gcpSelection = (vcpus: number) => ({
    ...selection,
    service_code: "6F81-5844-456A",
    sku: "CORE",
    usage_quantity: "24",
    product_family: "GCP > Compute > GCE",
    provider_options: options(vcpus),
  });
  const gcpArchitecture = (vcpus: number) =>
    ({
      ...architecture,
      provider: "gcp",
      collections: [
        {
          ...architecture.collections[0],
          region: "us-east1",
          sku_selections: [gcpSelection(vcpus)],
        },
      ],
    }) as unknown as ArchitectureDetail;
  const baseline = (vcpus: number) => ({
    service_code: "6F81-5844-456A",
    sku: "CORE",
    pricing_term: "on_demand" as const,
    purchase_option: "not_applicable" as const,
    usage_quantity: "24",
    region: "us-east1",
    provider_options: options(vcpus),
  });
  const legacyBaseline = (sku = "CORE", service_code = "6F81-5844-456A") => ({
    service_code,
    sku,
    pricing_term: "on_demand" as const,
    purchase_option: "not_applicable" as const,
    usage_quantity: "24",
  });

  function seed(prior: object, pricedContents: object[]) {
    localStorage.setItem(`cloud-pricing-prior-calculation-${ARCH_ID}`, JSON.stringify(prior));
    writePricingResult(ARCH_ID, {
      version: 1,
      result: { ...result("100"), duration: "1_month" },
      duration: "1_month",
      priceChange: null,
      pricedContents: pricedContents as never,
      calculatedAt: "2026-11-01T00:00:00.000Z",
    });
  }

  async function calculateAt(duration: "1_month" | "1_year") {
    await screen.findByText(/Total: .*100/);
    fireEvent.change(screen.getByLabelText("Duration"), { target: { value: duration } });
    fireEvent.click(screen.getByRole("button", { name: /^Calculate/ }));
  }

  beforeEach(() => {
    localStorage.clear();
    vi.spyOn(api, "listProviders").mockResolvedValue([]);
    vi.spyOn(api, "listRegions").mockResolvedValue([]);
    vi.spyOn(api, "listArchitectures").mockResolvedValue([]);
    vi.spyOn(api, "getCurrentUser").mockResolvedValue(
      null as unknown as Awaited<ReturnType<typeof api.getCurrentUser>>,
    );
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows new − previous after editing only vCPUs on a GCP machine", async () => {
    vi.spyOn(api, "getArchitecture").mockResolvedValue(gcpArchitecture(8));
    seed({ version: 2, total: "100", duration: "1_month", selections: [baseline(4)] }, [
      baseline(4),
    ]);
    vi.spyOn(api, "calculate").mockResolvedValue({ ...result("150"), duration: "1_month" });
    const snapshot = vi.spyOn(api, "calculateSnapshot");

    renderWorkspace();
    expect(
      await screen.findByText("Architecture has been updated since last pricing"),
    ).toBeInTheDocument();
    await calculateAt("1_month");

    expect(await screen.findByText(/Price Change: \+.*50/)).toBeInTheDocument();
    expect(snapshot).not.toHaveBeenCalled();
  });

  it("re-prices the previous contents with provider, region and options on a Duration switch", async () => {
    vi.spyOn(api, "getArchitecture").mockResolvedValue(gcpArchitecture(8));
    seed({ version: 2, total: "100", duration: "1_month", selections: [baseline(4)] }, [
      baseline(4),
    ]);
    vi.spyOn(api, "calculate").mockResolvedValue(result("1800"));
    const snapshot = vi.spyOn(api, "calculateSnapshot").mockResolvedValue(result("1200"));

    renderWorkspace();
    await calculateAt("1_year");

    expect(await screen.findByText(/Price Change: \+.*600/)).toBeInTheDocument();
    expect(snapshot).toHaveBeenCalledWith("1_year", [baseline(4)], "gcp");
  });

  it("shows 'Not available' for a legacy GCP baseline after a Duration switch, with no snapshot call", async () => {
    vi.spyOn(api, "getArchitecture").mockResolvedValue(gcpArchitecture(4));
    seed({ total: "100", duration: "1_month", selections: [legacyBaseline()] }, [
      { ...legacyBaseline(), region: "us-east1" },
    ]);
    vi.spyOn(api, "calculate").mockResolvedValue(result("1200"));
    const snapshot = vi.spyOn(api, "calculateSnapshot");

    renderWorkspace();
    // The upgrade alone doesn't mark the stored result out of date.
    await screen.findByText(/Total: .*100/);
    expect(screen.queryByText("Architecture has been updated since last pricing")).toBeNull();
    await calculateAt("1_year");

    expect(
      await screen.findByText(
        "Not available: previous calculation from prior version is unreliable",
      ),
    ).toBeInTheDocument();
    expect(snapshot).not.toHaveBeenCalled();
    const stored = JSON.parse(
      localStorage.getItem(`cloud-pricing-prior-calculation-${ARCH_ID}`) ?? "null",
    );
    expect(stored).toMatchObject({ version: 2, total: "1200", duration: "1_year" });
    expect(stored.selections).toEqual([baseline(4)]);
  });

  it("still re-prices a legacy AWS baseline after a Duration switch", async () => {
    vi.spyOn(api, "getArchitecture").mockResolvedValue(architecture);
    const awsLegacy = legacyBaseline("SKU1", "AmazonEC2");
    seed(
      { total: "100", duration: "1_month", selections: [{ ...awsLegacy, usage_quantity: "730" }] },
      [{ ...awsLegacy, usage_quantity: "730", region: "us-east-1" }],
    );
    vi.spyOn(api, "calculate").mockResolvedValue(result("1300"));
    const snapshot = vi.spyOn(api, "calculateSnapshot").mockResolvedValue(result("1200"));

    renderWorkspace();
    await calculateAt("1_year");

    expect(await screen.findByText(/Price Change: \+.*100/)).toBeInTheDocument();
    expect(snapshot).toHaveBeenCalledWith(
      "1_year",
      [{ ...awsLegacy, usage_quantity: "730" }],
      "aws",
    );
    expect(
      screen.queryByText("Not available: previous calculation from prior version is unreliable"),
    ).toBeNull();
  });
});
