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
  // Which of the two proration interpretations this quantity represents (004, FR-007) — only
  // meaningful for On-Demand (006-fix-reserved-pricing: usage_quantity has no Reserved-term
  // meaning at all, so the input isn't shown — and this hint isn't computed — once a Reserved
  // term is selected, below).
  const hint = usageQuantityHint(unit);

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
            if (value === "on_demand") {
              setPurchaseOption("not_applicable");
            } else {
              if (purchaseOption === "not_applicable") setPurchaseOption("no_upfront");
              // usage_quantity has no Reserved-term meaning (006, Clarifications) — its input
              // is hidden below, but the API field is still required, so reset it to a
              // harmless, self-consistent value rather than carrying over whatever was last
              // typed for an On-Demand selection (research.md §4).
              setQuantity("1");
            }
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

      {/* 006-fix-reserved-pricing, FR-007: usage_quantity has no Reserved-term meaning at all
          — showing it (even relabeled) invites exactly the mistake that produced the original
          bug report, so it's hidden outright rather than shown with different guidance. */}
      {term === "on_demand" && (
        <>
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
        </>
      )}

      <button type="submit">{submitLabel}</button>
    </form>
  );
}
