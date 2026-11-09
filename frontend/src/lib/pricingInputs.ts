/** 021 US5 (FR-037, FR-039): what the Service form starts with and submits, kept apart from
 * the form so a service can be added with the same defaults without it. */
import type { CatalogKind, PricingTerm, ProviderCode, PurchaseOption } from "../api/client";
import type { PricingInputs } from "../components/PricingInputsForm";
import type { AzureOs } from "../components/providers/AzureFields";
import { offeredPriceTypes } from "./providerPricing";

interface StoredOptions {
  kind: string;
  os?: string;
  vcpus?: number;
  memory_gib?: number | string;
  ram_sku?: string;
}

/** Pre-filled values, e.g. an existing SKU Selection's inputs. */
export type InitialInputs = Partial<Omit<PricingInputs, "provider_options">> & {
  provider_options?: StoredOptions | null;
};

export interface FormContext {
  initial?: InitialInputs;
  provider?: ProviderCode;
  priceTypes?: readonly PricingTerm[];
  kind?: CatalogKind | null;
  attributes?: Record<string, string>;
}

export interface FormState {
  term: PricingTerm;
  purchaseOption: PurchaseOption;
  quantity: string;
  os: AzureOs;
  vcpus: string;
  memoryGib: string;
}

/** Which provider fields the item has: an Azure VM's OS, or a GCP machine's vCPUs and memory. */
export function itemShape({ initial, provider = "aws", kind, attributes }: FormContext) {
  const stored = initial?.provider_options ?? null;
  const ramSku = stored?.ram_sku ?? attributes?.ram_sku ?? "";
  return {
    ramSku,
    isAzureVm: provider === "azure" && (kind === "vm" || stored?.kind === "azure_vm"),
    isGcpMachine:
      provider === "gcp" && Boolean(ramSku) && (kind === "vm" || stored?.kind === "gcp_machine"),
  };
}

/** What the form starts with: the stored values, or the defaults for a new service. */
export function initialState(ctx: FormContext): FormState {
  const { initial, provider = "aws", priceTypes } = ctx;
  const offered = offeredPriceTypes(provider, priceTypes);
  const wanted = initial?.pricing_term ?? "on_demand";
  const stored = initial?.provider_options ?? null;
  return {
    term: offered.includes(wanted) ? wanted : offered[0],
    purchaseOption: initial?.purchase_option ?? "not_applicable",
    quantity: initial?.usage_quantity ?? "730",
    os: stored?.os === "windows" ? "windows" : "linux",
    vcpus: String(stored?.vcpus ?? 4),
    memoryGib: String(stored?.memory_gib ?? 16),
  };
}

/** The request the form submits for a given state. */
export function inputsOf(state: FormState, ctx: FormContext): PricingInputs {
  const { isAzureVm, isGcpMachine, ramSku } = itemShape(ctx);
  const inputs: PricingInputs = {
    pricing_term: state.term,
    purchase_option: state.purchaseOption,
    usage_quantity: state.quantity,
  };
  // AWS keeps its request exactly as before; other providers always send their options.
  if ((ctx.provider ?? "aws") !== "aws") {
    inputs.provider_options = isAzureVm
      ? { kind: "azure_vm", version: 1, os: state.os }
      : isGcpMachine
        ? {
            kind: "gcp_machine",
            version: 1,
            vcpus: Number(state.vcpus),
            memory_gib: state.memoryGib,
            ram_sku: ramSku,
          }
        : null;
  }
  return inputs;
}

/** 021 US5 (FR-037): the inputs a new service gets when it is added without the form, the same
 * values an untouched form would submit. */
export function defaultPricingInputs(ctx: Omit<FormContext, "initial">): PricingInputs {
  return inputsOf(initialState(ctx), ctx);
}

export const sameInputs = (a: PricingInputs, b: PricingInputs) =>
  JSON.stringify(a) === JSON.stringify(b);
