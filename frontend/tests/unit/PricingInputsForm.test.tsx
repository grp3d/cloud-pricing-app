import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PricingInputsForm } from "../../src/components/PricingInputsForm";
import { defaultPricingInputs } from "../../src/lib/pricingInputs";

describe("PricingInputsForm", () => {
  it("submits on_demand with not_applicable purchase option by default", () => {
    const onSubmit = vi.fn();
    render(<PricingInputsForm onSubmit={onSubmit} />);

    fireEvent.click(screen.getByText("Add"));

    expect(onSubmit).toHaveBeenCalledWith({
      pricing_term: "on_demand",
      purchase_option: "not_applicable",
      usage_quantity: "730",
    });
  });

  it("only shows the purchase-option select for a reserved term", () => {
    render(<PricingInputsForm onSubmit={vi.fn()} />);
    expect(screen.queryByText("Purchase option")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Term"), { target: { value: "reserved_1yr" } });
    expect(screen.getByText("Purchase option")).toBeInTheDocument();
  });

  // 006-fix-reserved-pricing, FR-007: usage_quantity has no meaning for a Reserved term — the
  // input (and its hint) must be genuinely absent from the rendered form, not merely hidden by
  // CSS, so a user can't be misled into entering a value the way the original bug-reporting
  // user was.
  it("hides the usage-quantity input entirely once a Reserved term is selected", () => {
    render(<PricingInputsForm onSubmit={vi.fn()} unit="Hrs" />);
    expect(screen.getByLabelText(/Usage quantity/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Term"), { target: { value: "reserved_1yr" } });
    expect(screen.queryByLabelText(/Usage quantity/)).not.toBeInTheDocument();
    expect(screen.queryByText(/steady daily rate/)).not.toBeInTheDocument();
    expect(screen.queryByText(/billing period/)).not.toBeInTheDocument();
  });

  it("shows the usage-quantity input again when switching back to on_demand", () => {
    render(<PricingInputsForm onSubmit={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Term"), { target: { value: "reserved_1yr" } });
    fireEvent.change(screen.getByLabelText("Term"), { target: { value: "on_demand" } });
    expect(screen.getByLabelText(/Usage quantity/)).toBeInTheDocument();
  });

  it("submits a harmless quantity of 1 for a Reserved term, since the field is hidden", () => {
    const onSubmit = vi.fn();
    render(<PricingInputsForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText("Term"), { target: { value: "reserved_1yr" } });
    fireEvent.click(screen.getByText("Add"));

    expect(onSubmit).toHaveBeenCalledWith({
      pricing_term: "reserved_1yr",
      purchase_option: "no_upfront",
      usage_quantity: "1",
    });
  });
});

describe("defaultPricingInputs (021 US5, FR-037)", () => {
  it.each([
    ["aws", undefined, undefined],
    ["azure", "vm", undefined],
    ["gcp", "vm", { ram_sku: "RAM-1" }],
    ["gcp", null, undefined],
  ] as const)("matches an untouched %s form (kind %s)", (provider, kind, attributes) => {
    const onSubmit = vi.fn();
    render(
      <PricingInputsForm
        onSubmit={onSubmit}
        provider={provider}
        kind={kind}
        attributes={attributes}
      />,
    );
    fireEvent.click(screen.getByText("Add"));
    expect(onSubmit).toHaveBeenCalledWith(defaultPricingInputs({ provider, kind, attributes }));
  });

  it("gives an Azure VM Linux and a GCP machine 4 vCPUs and 16 GiB", () => {
    expect(defaultPricingInputs({ provider: "azure", kind: "vm" }).provider_options).toEqual({
      kind: "azure_vm",
      version: 1,
      os: "linux",
    });
    expect(
      defaultPricingInputs({ provider: "gcp", kind: "vm", attributes: { ram_sku: "R" } })
        .provider_options,
    ).toEqual({ kind: "gcp_machine", version: 1, vcpus: 4, memory_gib: "16", ram_sku: "R" });
  });
});

describe("Save button colour (021 US5, FR-039)", () => {
  const initial = {
    pricing_term: "on_demand" as const,
    purchase_option: "not_applicable" as const,
    usage_quantity: "730",
  };
  const save = () => screen.getByRole("button", { name: /Save/ });
  const quantity = () => screen.getByLabelText(/Usage quantity/);

  it("is light blue until a field changes, then dark blue", () => {
    render(<PricingInputsForm submitLabel="Save" initial={initial} onSubmit={vi.fn()} />);
    expect(save()).toHaveAttribute("data-variant", "soft");
    fireEvent.change(quantity(), { target: { value: "100" } });
    expect(save()).toHaveAttribute("data-variant", "default");
    fireEvent.change(quantity(), { target: { value: "730" } });
    expect(save()).toHaveAttribute("data-variant", "soft");
  });

  it("is clickable while light blue", () => {
    const onSubmit = vi.fn();
    render(<PricingInputsForm submitLabel="Save" initial={initial} onSubmit={onSubmit} />);
    fireEvent.click(save());
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("turns light blue after a successful save, and stays dark after a failed one", async () => {
    const onSubmit = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    render(<PricingInputsForm submitLabel="Save" initial={initial} onSubmit={onSubmit} />);
    fireEvent.change(quantity(), { target: { value: "100" } });
    fireEvent.click(save());
    await vi.waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(save()).toHaveAttribute("data-variant", "default");
    fireEvent.click(save());
    await vi.waitFor(() => expect(save()).toHaveAttribute("data-variant", "soft"));
  });

  it("an Add form is always the primary style", () => {
    render(<PricingInputsForm onSubmit={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Add/ })).toHaveAttribute("data-variant", "default");
  });
});
