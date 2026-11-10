import { fireEvent, render, screen, within } from "@testing-library/react";
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

// --- 019 (T057, FR-005, FR-005a): provider fields ----------------------------------------------

describe("ServiceConfigPanel — provider fields", () => {
  const azureVm = sku({
    id: "az-vm",
    service_code: "DZH313Z7MMC8",
    sku: "DZH318Z08M9W/004T/db8c",
    unit: "1 Hour",
    usage_quantity: "24",
    price_types: ["on_demand", "reserved_1yr", "savings_plan_1yr"],
    kind: "vm",
    provider_options: { kind: "azure_vm", version: 1, os: "windows" },
  });

  it("offers only the item's published price types and Azure's OS, without AWS fields", () => {
    render(
      panel({
        ...noop,
        provider: "azure",
        selection: existingServiceSelection("az-vm"),
        resolvedExisting: azureVm,
      }),
    );
    const terms = Array.from(
      (screen.getByLabelText("Term") as HTMLSelectElement).options,
      (o) => o.value,
    );
    expect(terms).toEqual(["on_demand", "reserved_1yr", "savings_plan_1yr"]);
    expect(screen.getByLabelText("Operating system")).toHaveValue("windows");
    expect(screen.queryByLabelText("Purchase option")).toBeNull();
  });

  it("submits Azure's options and never a purchase option", () => {
    const onSubmitExisting = vi.fn();
    render(
      panel({
        ...noop,
        onSubmitExisting,
        provider: "azure",
        selection: existingServiceSelection("az-vm"),
        resolvedExisting: azureVm,
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: /Save/ }));
    expect(onSubmitExisting).toHaveBeenCalledWith("az-vm", {
      pricing_term: "on_demand",
      purchase_option: "not_applicable",
      usage_quantity: "24",
      provider_options: { kind: "azure_vm", version: 1, os: "windows" },
    });
  });

  it("shows a GCP machine's vCPUs and memory and commitment terms", () => {
    const onSubmitExisting = vi.fn();
    const core = sku({
      id: "gcp-core",
      service_code: "6F81-5844-456A",
      sku: "BB77-5FDA-69D9",
      unit: "h",
      usage_quantity: "24",
      price_types: ["on_demand", "commitment_1yr", "commitment_3yr"],
      kind: "vm",
      attributes: { ram_sku: "5B01-D157-A097" },
      provider_options: {
        kind: "gcp_machine",
        version: 1,
        vcpus: 4,
        memory_gib: "16",
        ram_sku: "5B01-D157-A097",
      },
    });
    render(
      panel({
        ...noop,
        onSubmitExisting,
        provider: "gcp",
        selection: existingServiceSelection("gcp-core"),
        resolvedExisting: core,
      }),
    );
    expect(screen.getByLabelText("vCPUs")).toHaveValue(4);
    expect(screen.getByLabelText("Memory (GiB)")).toHaveValue(16);
    expect(screen.getByLabelText("Hours per day")).toHaveValue(24);
    fireEvent.change(screen.getByLabelText("vCPUs"), { target: { value: "8" } });
    fireEvent.change(screen.getByLabelText("Term"), { target: { value: "commitment_1yr" } });
    fireEvent.click(screen.getByRole("button", { name: /Save/ }));
    expect(onSubmitExisting).toHaveBeenCalledWith("gcp-core", {
      pricing_term: "commitment_1yr",
      purchase_option: "not_applicable",
      usage_quantity: "24",
      provider_options: {
        kind: "gcp_machine",
        version: 1,
        vcpus: 8,
        memory_gib: "16",
        ram_sku: "5B01-D157-A097",
      },
    });
  });

  it("keeps AWS's fields and request unchanged", () => {
    const onSubmitExisting = vi.fn();
    render(
      panel({
        ...noop,
        onSubmitExisting,
        selection: existingServiceSelection("sku-a"),
        resolvedExisting: sku({ pricing_term: "reserved_1yr", purchase_option: "all_upfront" }),
      }),
    );
    const terms = Array.from(
      (screen.getByLabelText("Term") as HTMLSelectElement).options,
      (o) => o.value,
    );
    expect(terms).toEqual(["on_demand", "reserved_1yr", "reserved_3yr"]);
    expect(screen.getByLabelText("Purchase option")).toHaveValue("all_upfront");
    fireEvent.click(screen.getByRole("button", { name: /Save/ }));
    expect(onSubmitExisting.mock.calls[0][1]).not.toHaveProperty("provider_options");
  });
});

// --- 021 (FR-018): the Service tab's empty prompt --------------------------------------------

describe("ServiceConfigPanel as the inspector's Service tab (021)", () => {
  it("prompts to select a service when nothing is selected", () => {
    render(panel({ ...noop, selection: null, resolvedExisting: null }));
    expect(screen.getByText("Select a service on the canvas")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });

  it("treats a selection whose service no longer exists as nothing selected", () => {
    render(panel({ ...noop, selection: existingServiceSelection("gone"), resolvedExisting: null }));
    expect(screen.getByText("Select a service on the canvas")).toBeInTheDocument();
  });
});

// --- 021 US7 (FR-046): a readable heading, with the codes muted -------------------------------

describe("ServiceConfigPanel heading (021 US7)", () => {
  it("names a GCP service by its name and description, and lists its category", () => {
    const gcp = sku({
      id: "gcs",
      service_code: "95FF-2EF5-5EA1",
      sku: "EE2C-E844-D760",
      service_name: "Cloud Storage",
      summary: "Multi-Region HNS Nearline Class A Operations",
      product_family: "Storage > GCS > Ops > Nearline > Multi-Region",
      attributes: { location: "global" },
    });
    render(
      panel({
        ...noop,
        provider: "gcp",
        selection: existingServiceSelection("gcs"),
        resolvedExisting: gcp,
      }),
    );
    const heading = screen.getByRole("heading", { level: 3 });
    expect(heading).toHaveTextContent("Cloud Storage");
    expect(heading).toHaveTextContent("Multi-Region HNS Nearline Class A Operations");
    const codes = screen.getByText("95FF-2EF5-5EA1 / EE2C-E844-D760");
    expect(codes).toHaveClass("text-muted-foreground");
    expect(heading).not.toHaveTextContent("95FF-2EF5-5EA1");
    expect(screen.getByText("category")).toBeInTheDocument();
    expect(screen.getByText("Storage > GCS > Ops > Nearline > Multi-Region")).toBeInTheDocument();
  });

  it("keeps an AWS service's code, with its identifying details as the description", () => {
    render(
      panel({
        ...noop,
        selection: existingServiceSelection("sku-a"),
        resolvedExisting: sku({ attributes: { instanceType: "m5.large", vcpu: "2" } }),
      }),
    );
    const heading = screen.getByRole("heading", { level: 3 });
    expect(heading).toHaveTextContent("AmazonEC2");
    expect(heading).toHaveTextContent("m5.large · 2");
    expect(screen.getByText("AmazonEC2 / SKU-A")).toHaveClass("text-muted-foreground");
  });
});

// --- 021 US8 (FR-049): the heading stays pinned while the rest scrolls -----------------------

describe("ServiceConfigPanel pinned heading (021 US8)", () => {
  it("pins the heading, codes and delete button above a divider; the form scrolls", () => {
    render(
      panel({
        ...noop,
        selection: existingServiceSelection("sku-a"),
        resolvedExisting: sku({ attributes: { instanceType: "m5.large" } }),
      }),
    );
    const pinned = screen.getByTestId("service-pinned");
    const scroll = screen.getByTestId("service-scroll");
    expect(within(pinned).getByRole("heading", { level: 3 })).toHaveTextContent("AmazonEC2");
    expect(within(pinned).getByText("AmazonEC2 / SKU-A")).toBeInTheDocument();
    expect(within(pinned).getByRole("button", { name: "Remove this service" })).toBeInTheDocument();
    expect(pinned.querySelector('[data-slot="separator"]')).not.toBeNull();
    expect(pinned).toHaveClass("shrink-0");
    expect(within(scroll).getByRole("button", { name: /Save/ })).toBeInTheDocument();
    expect(within(scroll).getByLabelText(/Usage quantity/)).toBeInTheDocument();
    expect(scroll).toHaveClass("overflow-auto");
  });
});
