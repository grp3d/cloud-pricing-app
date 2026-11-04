/**
 * Provider-specific pricing choices for the Service Editor and catalog search (019, research R6,
 * FR-005, FR-005a). The backend validates every choice again; this only decides what to offer.
 */
import type { CatalogKind, PricingTerm, Provider, ProviderCode } from "../api/client";

/** The price types each provider supports (research R6 table, mirrors the backend). */
export const PROVIDER_PRICE_TYPES: Record<ProviderCode, PricingTerm[]> = {
  aws: ["on_demand", "reserved_1yr", "reserved_3yr"],
  azure: ["on_demand", "reserved_1yr", "reserved_3yr", "savings_plan_1yr", "savings_plan_3yr"],
  gcp: ["on_demand", "commitment_1yr", "commitment_3yr"],
};

export const PRICE_TYPE_LABELS: Record<PricingTerm, string> = {
  on_demand: "On-Demand",
  reserved_1yr: "1-Year Reserved",
  reserved_3yr: "3-Year Reserved",
  savings_plan_1yr: "1-Year Savings Plan",
  savings_plan_3yr: "3-Year Savings Plan",
  commitment_1yr: "1-Year Committed Use",
  commitment_3yr: "3-Year Committed Use",
};

export const CATALOG_KIND_LABELS: Record<CatalogKind, string> = {
  vm: "Virtual machines",
  block_storage: "Block storage",
  object_storage: "Object storage",
  data_transfer: "Data transfer",
  managed_db: "Managed databases",
};

export function asProviderCode(code: string | null | undefined): ProviderCode {
  return code === "gcp" || code === "azure" ? code : "aws";
}

/** The price types to offer for one item: those it publishes when the provider reports them
 * (Azure, GCP), else every type the provider supports (AWS). Always in the provider's order. */
export function offeredPriceTypes(
  provider: ProviderCode,
  published: readonly PricingTerm[] | null | undefined,
): PricingTerm[] {
  const all = PROVIDER_PRICE_TYPES[provider];
  if (!published || published.length === 0) return all;
  const offered = all.filter((t) => published.includes(t));
  return offered.length > 0 ? offered : all;
}

/** A term priced as a whole-term commitment: usage quantity has no meaning (006). Azure
 * reservations are priced the same way (research R6). */
export function isTermPriced(term: PricingTerm): boolean {
  return term === "reserved_1yr" || term === "reserved_3yr";
}

/** AWS reservations have purchase options; no other provider's prices do (research R6). */
export function hasPurchaseOptions(provider: ProviderCode, term: PricingTerm): boolean {
  return provider === "aws" && isTermPriced(term);
}

/** The hover text for a provider button (FR-001): its snapshot date, or why it's disabled. */
export function providerHint(p: Provider): string {
  if (!p.active) return `${p.name}: ${p.reason ?? "not available"}`;
  const snapshot = p.snapshot_date ? `pricing snapshot ${p.snapshot_date}` : "pricing available";
  return p.reason ? `${p.name}: ${snapshot} (${p.reason})` : `${p.name}: ${snapshot}`;
}

/** Search-field placeholders per provider (contracts §3: `service_code` and `product_family`
 * mean each provider's own service id and grouping). */
export const SEARCH_PLACEHOLDERS: Record<ProviderCode, { service: string; group: string }> = {
  aws: {
    service: "Service code (e.g. AmazonEC2)",
    group: "Product family (e.g. Compute Instance)",
  },
  azure: { service: "Service (e.g. Virtual Machines)", group: "Product (e.g. Managed Disks)" },
  gcp: { service: "Service (e.g. Compute Engine)", group: "Category (e.g. Compute > GCE)" },
};

/** A region's label in pickers: its code, plus the provider's own name when it has one
 * (Azure `eastus` → "eastus — US East", contracts §2). */
export function regionLabel(r: { code: string; display_name?: string | null }): string {
  return r.display_name && r.display_name !== r.code ? `${r.code} — ${r.display_name}` : r.code;
}

export const PROVIDER_LABELS: Record<ProviderCode, string> = {
  aws: "AWS",
  gcp: "GCP",
  azure: "Azure",
};
