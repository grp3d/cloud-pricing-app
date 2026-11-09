import { Plus, Save } from "lucide-react";
import { useState } from "react";

import type {
  CatalogKind,
  PricingTerm,
  ProviderCode,
  ProviderOptions,
  PurchaseOption,
} from "../api/client";
import {
  PRICE_TYPE_LABELS,
  hasPurchaseOptions,
  isTermPriced,
  offeredPriceTypes,
} from "../lib/providerPricing";
import {
  type FormContext,
  type InitialInputs,
  initialState,
  inputsOf,
  itemShape,
  sameInputs,
} from "../lib/pricingInputs";
import { usageQuantityHint } from "../lib/usageQuantityHint";
import { AwsFields } from "./providers/AwsFields";
import { type AzureOs, AzureFields } from "./providers/AzureFields";
import { labelClassName, selectClassName } from "./providers/fieldStyles";
import { GcpFields } from "./providers/GcpFields";
import { Button } from "./ui/button";

export interface PricingInputs {
  pricing_term: PricingTerm;
  purchase_option: PurchaseOption;
  usage_quantity: string;
  /** 019 (research R6): the provider's typed options, or null for the common path. */
  provider_options?: ProviderOptions | null;
}

interface Props {
  /** Resolving to `false` means the submit failed, so Save stays dark blue (021 US5). */
  onSubmit: (inputs: PricingInputs) => void | boolean | Promise<void | boolean>;
  submitLabel?: string;
  /** Pre-fill the form, e.g. when editing an existing SKU Selection's inputs. */
  initial?: InitialInputs;
  /** The SKU's real billing unit (e.g. "Hrs", "GB-Mo") — shown alongside the usage-quantity
   * field so a user knows what they're entering a quantity of (003-service-selection-
   * improvements, FR-004/FR-005). `null`/undefined when unavailable — no fabricated unit. */
  unit?: string | null;
  /** 019: the architecture's provider (default AWS). */
  provider?: ProviderCode;
  /** 019 (FR-005): the price types this item publishes; empty means every type the provider
   * supports (AWS doesn't report them per item). */
  priceTypes?: readonly PricingTerm[];
  /** 019: the item's catalog kind (`vm` turns on the OS or machine fields). */
  kind?: CatalogKind | null;
  /** 019: the item's catalog attributes (a GCP core SKU names its RAM SKU, `ram_sku`). */
  attributes?: Record<string, string>;
}

/** Pricing inputs (FR-007): price type, purchase option, and usage quantity — the things a SKU
 * selection needs beyond which SKU it is. Also reused, via `initial`, to edit an existing SKU
 * Selection's inputs.
 *
 * 019 (FR-005, FR-005a): only the item's published price types are offered, AWS-only fields
 * (purchase option) are shown for AWS only, and the provider's own fields come from
 * `providers/*Fields` — an Azure VM's OS, a GCP machine's vCPUs and memory. */
export function PricingInputsForm({
  onSubmit,
  submitLabel = "Add",
  initial,
  unit,
  provider = "aws",
  priceTypes,
  kind,
  attributes,
}: Props) {
  const ctx: FormContext = { initial, provider, priceTypes, kind, attributes };
  const offered = offeredPriceTypes(provider, priceTypes);
  const [start] = useState(() => initialState(ctx));
  const [term, setTerm] = useState<PricingTerm>(start.term);
  const [purchaseOption, setPurchaseOption] = useState<PurchaseOption>(start.purchaseOption);
  const [quantity, setQuantity] = useState(start.quantity);
  const [os, setOs] = useState<AzureOs>(start.os);
  const [vcpus, setVcpus] = useState(start.vcpus);
  const [memoryGib, setMemoryGib] = useState(start.memoryGib);
  const { isAzureVm, isGcpMachine } = itemShape(ctx);

  const current = inputsOf({ term, purchaseOption, quantity, os, vcpus, memoryGib }, ctx);
  // 021 US5 (FR-039): Save is dark blue only when something differs from the saved service:
  // what it was opened with, or once saved here, what was last saved successfully (so it
  // turns light blue straight away, before the refetch lands).
  const [lastSaved, setLastSaved] = useState<PricingInputs | null>(null);
  const changed = !sameInputs(current, lastSaved ?? inputsOf(start, ctx));
  const submitVariant = submitLabel === "Save" && !changed ? "soft" : "default";

  // Which of the two proration interpretations this quantity represents (004, FR-007) — only
  // meaningful for usage-priced terms (006-fix-reserved-pricing: usage_quantity has no
  // Reserved-term meaning at all, so the input isn't shown — and this hint isn't computed —
  // once a Reserved term is selected, below).
  const hint = usageQuantityHint(isGcpMachine ? "Hrs" : unit);

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        const submitted = current;
        void Promise.resolve(onSubmit(submitted)).then((ok) => {
          if (ok !== false) setLastSaved(submitted);
        });
      }}
    >
      <label className={labelClassName}>
        Term
        <select
          className={selectClassName}
          value={term}
          onChange={(e) => {
            const value = e.target.value as PricingTerm;
            setTerm(value);
            if (hasPurchaseOptions(provider, value)) {
              if (purchaseOption === "not_applicable") setPurchaseOption("no_upfront");
            } else {
              setPurchaseOption("not_applicable");
            }
            if (isTermPriced(value)) {
              // usage_quantity has no Reserved-term meaning (006, Clarifications) — its input
              // is hidden below, but the API field is still required, so reset it to a
              // harmless, self-consistent value rather than carrying over whatever was last
              // typed for an On-Demand selection (research.md §4).
              setQuantity("1");
            }
          }}
        >
          {offered.map((t) => (
            <option key={t} value={t}>
              {PRICE_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
      </label>

      {provider === "aws" && (
        <AwsFields
          term={term}
          purchaseOption={purchaseOption}
          onPurchaseOptionChange={setPurchaseOption}
        />
      )}
      {provider === "azure" && <AzureFields isVm={isAzureVm} os={os} onOsChange={setOs} />}
      {provider === "gcp" && (
        <GcpFields
          isMachine={isGcpMachine}
          vcpus={vcpus}
          memoryGib={memoryGib}
          onVcpusChange={setVcpus}
          onMemoryGibChange={setMemoryGib}
        />
      )}

      {/* 006-fix-reserved-pricing, FR-007: usage_quantity has no Reserved-term meaning at all
          — showing it (even relabeled) invites exactly the mistake that produced the original
          bug report, so it's hidden outright rather than shown with different guidance. */}
      {!isTermPriced(term) && (
        <>
          <label className={labelClassName}>
            {isGcpMachine ? "Hours per day" : `Usage quantity${unit ? ` (${unit})` : ""}`}
            <input
              className="rounded-md border border-input bg-background px-1.5 py-1 text-xs"
              type="number"
              min="0"
              step="any"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
          </label>
          {hint === "per_day_estimate" && (
            <p className="text-2xs text-muted-foreground">
              Enter a steady daily rate — the Calculate duration scales this up.
            </p>
          )}
          {hint === "period_denominated" && (
            <p className="text-2xs text-muted-foreground">
              Enter the SKU's own quantity for its billing period — not scaled by duration.
            </p>
          )}
        </>
      )}

      <Button type="submit" size="sm" variant={submitVariant} className="self-start">
        {submitLabel === "Save" ? <Save /> : <Plus />} {submitLabel}
      </Button>
    </form>
  );
}
