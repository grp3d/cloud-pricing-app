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
});
