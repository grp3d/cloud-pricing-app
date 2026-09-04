import { useState } from "react";

import type { PricingTerm, PurchaseOption } from "../api/client";

export interface PricingInputs {
  pricing_term: PricingTerm;
  purchase_option: PurchaseOption;
  usage_quantity: string;
}

interface Props {
  onSubmit: (inputs: PricingInputs) => void;
  submitLabel?: string;
}

/** Pricing inputs (FR-007): commitment term, purchase option, and usage quantity — the three
 * things a SKU selection needs beyond which SKU it is. */
export function PricingInputsForm({ onSubmit, submitLabel = "Add" }: Props) {
  const [term, setTerm] = useState<PricingTerm>("on_demand");
  const [purchaseOption, setPurchaseOption] = useState<PurchaseOption>("not_applicable");
  const [quantity, setQuantity] = useState("730");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ pricing_term: term, purchase_option: purchaseOption, usage_quantity: quantity });
      }}
    >
      <label>
        Term{" "}
        <select
          value={term}
          onChange={(e) => {
            const value = e.target.value as PricingTerm;
            setTerm(value);
            if (value === "on_demand") setPurchaseOption("not_applicable");
            else if (purchaseOption === "not_applicable") setPurchaseOption("no_upfront");
          }}
        >
          <option value="on_demand">On-Demand</option>
          <option value="reserved_1yr">1-Year Reserved</option>
          <option value="reserved_3yr">3-Year Reserved</option>
        </select>
      </label>

      {term !== "on_demand" && (
        <label>
          Purchase option{" "}
          <select
            value={purchaseOption}
            onChange={(e) => setPurchaseOption(e.target.value as PurchaseOption)}
          >
            <option value="no_upfront">No Upfront</option>
            <option value="partial_upfront">Partial Upfront</option>
            <option value="all_upfront">All Upfront</option>
          </select>
        </label>
      )}

      <label>
        Usage quantity{" "}
        <input
          type="number"
          min="0"
          step="any"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
        />
      </label>

      <button type="submit">{submitLabel}</button>
    </form>
  );
}
