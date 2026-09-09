import { useState } from "react";

import type { PricingTerm, PurchaseOption } from "../api/client";
import { usageQuantityHint } from "../lib/usageQuantityHint";

export interface PricingInputs {
  pricing_term: PricingTerm;
  purchase_option: PurchaseOption;
  usage_quantity: string;
}

interface Props {
  onSubmit: (inputs: PricingInputs) => void;
  submitLabel?: string;
  /** Pre-fill the form, e.g. when editing an existing SKU Selection's inputs. */
  initial?: Partial<PricingInputs>;
  /** The SKU's real billing unit (e.g. "Hrs", "GB-Mo") — shown alongside the usage-quantity
   * field so a user knows what they're entering a quantity of (003-service-selection-
   * improvements, FR-004/FR-005). `null`/undefined when unavailable — no fabricated unit. */
  unit?: string | null;
}

/** Pricing inputs (FR-007): commitment term, purchase option, and usage quantity — the three
 * things a SKU selection needs beyond which SKU it is. Also reused, via `initial`, to edit an
 * existing SKU Selection's inputs. */
export function PricingInputsForm({ onSubmit, submitLabel = "Add", initial, unit }: Props) {
  const [term, setTerm] = useState<PricingTerm>(initial?.pricing_term ?? "on_demand");
  const [purchaseOption, setPurchaseOption] = useState<PurchaseOption>(
    initial?.purchase_option ?? "not_applicable",
  );
  const [quantity, setQuantity] = useState(initial?.usage_quantity ?? "730");
  // Which of the two proration interpretations this quantity represents (004, FR-007) —
  // recomputed live as the user changes Term, since half the answer (Reserved vs. on-demand)
  // depends on that.
  const hint = usageQuantityHint(term, unit);

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
        Usage quantity{unit ? ` (${unit})` : ""}{" "}
        <input
          type="number"
          min="0"
          step="any"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
        />
      </label>
      {hint === "per_day_estimate" && (
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "#6b7280" }}>
          Enter a steady daily rate — the Calculate duration scales this up.
        </p>
      )}
      {hint === "period_denominated" && (
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "#6b7280" }}>
          Enter the SKU's own quantity for its billing period — not scaled by duration.
        </p>
      )}

      <button type="submit">{submitLabel}</button>
    </form>
  );
}
