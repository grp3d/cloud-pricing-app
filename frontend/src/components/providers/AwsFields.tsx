import type { PricingTerm, PurchaseOption } from "../../api/client";
import { isTermPriced } from "../../lib/providerPricing";
import { labelClassName, selectClassName } from "./fieldStyles";

interface Props {
  term: PricingTerm;
  purchaseOption: PurchaseOption;
  onPurchaseOptionChange: (value: PurchaseOption) => void;
}

/** AWS-only Service Editor fields (019, FR-005a): the purchase option of a reservation. */
export function AwsFields({ term, purchaseOption, onPurchaseOptionChange }: Props) {
  if (!isTermPriced(term)) return null;
  return (
    <label className={labelClassName}>
      Purchase option
      <select
        className={selectClassName}
        value={purchaseOption}
        onChange={(e) => onPurchaseOptionChange(e.target.value as PurchaseOption)}
      >
        <option value="no_upfront">No Upfront</option>
        <option value="partial_upfront">Partial Upfront</option>
        <option value="all_upfront">All Upfront</option>
      </select>
    </label>
  );
}
