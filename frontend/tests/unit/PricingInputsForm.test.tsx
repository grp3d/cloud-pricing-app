import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PricingInputsForm } from "../../src/components/PricingInputsForm";

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
