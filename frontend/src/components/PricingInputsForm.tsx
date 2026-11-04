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

interface StoredOptions {
  kind: string;
  os?: string;
  vcpus?: number;
  memory_gib?: number | string;
  ram_sku?: string;
}

interface Props {
  onSubmit: (inputs: PricingInputs) => void;
  submitLabel?: string;
  /** Pre-fill the form, e.g. when editing an existing SKU Selection's inputs. */
  initial?: Partial<Omit<PricingInputs, "provider_options">> & {
    provider_options?: StoredOptions | null;
  };
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
  const offered = offeredPriceTypes(provider, priceTypes);
  const [term, setTerm] = useState<PricingTerm>(() => {
    const wanted = initial?.pricing_term ?? "on_demand";
    return offered.includes(wanted) ? wanted : offered[0];
  });
  const [purchaseOption, setPurchaseOption] = useState<PurchaseOption>(
    initial?.purchase_option ?? "not_applicable",
  );
  const [quantity, setQuantity] = useState(initial?.usage_quantity ?? "730");

  const stored = initial?.provider_options ?? null;
  const [os, setOs] = useState<AzureOs>(stored?.os === "windows" ? "windows" : "linux");
  const ramSku = stored?.ram_sku ?? attributes?.ram_sku ?? "";
  const [vcpus, setVcpus] = useState(String(stored?.vcpus ?? 4));
  const [memoryGib, setMemoryGib] = useState(String(stored?.memory_gib ?? 16));

  const isAzureVm = provider === "azure" && (kind === "vm" || stored?.kind === "azure_vm");
  const isGcpMachine =
    provider === "gcp" && Boolean(ramSku) && (kind === "vm" || stored?.kind === "gcp_machine");

  // Which of the two proration interpretations this quantity represents (004, FR-007) — only
  // meaningful for usage-priced terms (006-fix-reserved-pricing: usage_quantity has no
  // Reserved-term meaning at all, so the input isn't shown — and this hint isn't computed —
  // once a Reserved term is selected, below).
  const hint = usageQuantityHint(isGcpMachine ? "Hrs" : unit);

  function options(): ProviderOptions | null {
    if (isAzureVm) return { kind: "azure_vm", version: 1, os };
    if (isGcpMachine) {
      return {
        kind: "gcp_machine",
        version: 1,
        vcpus: Number(vcpus),
        memory_gib: memoryGib,
        ram_sku: ramSku,
      };
    }
    return null;
  }

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        const inputs: PricingInputs = {
          pricing_term: term,
          purchase_option: purchaseOption,
          usage_quantity: quantity,
        };
        // AWS keeps its request exactly as before; other providers always send their options.
        if (provider !== "aws") inputs.provider_options = options();
        onSubmit(inputs);
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
              className="rounded border border-border bg-background px-1.5 py-1 text-xs"
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

      <Button type="submit" size="sm" className="self-start">
        {submitLabel === "Save" ? <Save /> : <Plus />} {submitLabel}
      </Button>
    </form>
  );
}
