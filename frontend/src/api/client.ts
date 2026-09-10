/**
 * Thin typed fetch wrapper over the backend API. Types come entirely from `generated/schema.d.ts`
 * (regenerated from the backend's live OpenAPI schema — Constitution Principle IV: no
 * hand-maintained request/response shapes). This file adds no new shapes of its own.
 */
import type { components } from "./generated/schema.d.ts";

export type Provider = components["schemas"]["ProviderOut"];
export type ArchitectureSummary = components["schemas"]["ArchitectureSummaryOut"];
export type ArchitectureDetail = components["schemas"]["ArchitectureDetailOut"];
export type Collection = components["schemas"]["CollectionOut"];
export type DataConnector = components["schemas"]["DataConnectorOut"];
export type SKUSelection = components["schemas"]["SKUSelectionOut"];
export type CatalogSKU = components["schemas"]["CatalogSKUOut"];
export type CatalogSearchResult = components["schemas"]["CatalogSearchResult"];
export type CalculationResult = components["schemas"]["CalculationResult"];
export type CalculationDuration = components["schemas"]["CalculationDuration"];
export type CollectionType = components["schemas"]["CollectionType"];
export type PricingTerm = components["schemas"]["PricingTerm"];
export type PurchaseOption = components["schemas"]["PurchaseOption"];
export type SnapshotSelection = components["schemas"]["SnapshotSelection"];

const BASE = "/api/v1";

/** The v1 placeholder identity (spec FR-002 / research.md): a stable per-browser user id,
 * sent as a bearer token. No login UI yet — see research.md for why. */
function getUserId(): string {
  const key = "cloud-pricing-user-id";
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(key, id);
  }
  return id;
}

/** Raised when the pricing data source itself is unavailable (HTTP 503) — kept structurally
 * distinct from an empty/"no results" response so the UI never conflates the two. */
export class PricingDataUnavailableError extends Error {}

/** Raised when a catalog search field's regex pattern is malformed (008-ui-updates-
 * corrections, FR-021, contracts/api.md) — `field` names which of `service_code`/
 * `product_family`/`text` the bad pattern came from, so the caller can show the message
 * inline next to that field rather than as a generic banner. */
export class InvalidRegexPatternError extends Error {
  field: "service_code" | "product_family" | "text";

  constructor(message: string, field: "service_code" | "product_family" | "text") {
    super(message);
    this.field = field;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getUserId()}`,
      ...init?.headers,
    },
  });

  if (res.status === 503) {
    const body = await res.json().catch(() => ({}));
    throw new PricingDataUnavailableError(
      body.message ?? "The AWS pricing data source is temporarily unreachable.",
    );
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    if (body.error === "invalid_regex_pattern") {
      throw new InvalidRegexPatternError(body.message ?? "Invalid pattern.", body.field);
    }
    throw new Error(body.detail ?? body.message ?? `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listProviders: () => request<Provider[]>("/providers"),

  listArchitectures: (provider = "aws") =>
    request<ArchitectureSummary[]>(`/architectures?provider=${provider}`),
  getArchitecture: (id: string) => request<ArchitectureDetail>(`/architectures/${id}`),
  createArchitecture: (name: string, provider = "aws") =>
    request<ArchitectureSummary>("/architectures", {
      method: "POST",
      body: JSON.stringify({ name, provider }),
    }),
  deleteArchitecture: (id: string) =>
    request<void>(`/architectures/${id}`, { method: "DELETE" }),

  createCollection: (architectureId: string, type: CollectionType, name: string) =>
    request<Collection>(`/architectures/${architectureId}/collections`, {
      method: "POST",
      body: JSON.stringify({ type, name }),
    }),
  deleteCollection: (id: string) => request<void>(`/collections/${id}`, { method: "DELETE" }),
  /** Nest, move, or un-nest an Application Component (002-vpc-component-nesting, FR-001-003).
   * Pass a VPC's id to nest/move into it, or `null` to un-nest back to top-level. */
  updateCollectionParent: (id: string, parentCollectionId: string | null) =>
    request<Collection>(`/collections/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ parent_collection_id: parentCollectionId }),
    }),

  searchCatalog: (params: { service_code?: string; product_family?: string; q?: string }) => {
    // 008-ui-updates-corrections, FR-023: request the backend's own maximum (200, matched
    // exactly — research.md §4) instead of its 50-row default.
    const entries = Object.entries(params).filter(([, v]) => v) as [string, string][];
    const qs = new URLSearchParams([...entries, ["limit", "200"]]);
    return request<CatalogSearchResult>(`/catalog/skus?${qs.toString()}`);
  },

  addSkuSelection: (
    collectionId: string,
    body: {
      service_code: string;
      sku: string;
      pricing_term: PricingTerm;
      purchase_option: PurchaseOption;
      usage_quantity: string;
    },
  ) =>
    request<SKUSelection>(`/collections/${collectionId}/sku-selections`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateSkuSelection: (
    id: string,
    body: Partial<{
      pricing_term: PricingTerm;
      purchase_option: PurchaseOption;
      usage_quantity: string;
    }>,
  ) =>
    request<SKUSelection>(`/sku-selections/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteSkuSelection: (id: string) =>
    request<void>(`/sku-selections/${id}`, { method: "DELETE" }),

  createConnector: (architectureId: string, fromCollectionId: string, toCollectionId: string) =>
    request<DataConnector>(`/architectures/${architectureId}/connectors`, {
      method: "POST",
      body: JSON.stringify({
        from_collection_id: fromCollectionId,
        to_collection_id: toCollectionId,
      }),
    }),
  deleteConnector: (id: string) => request<void>(`/connectors/${id}`, { method: "DELETE" }),
  attachConnectorSku: (
    connectorId: string,
    body: {
      service_code: string;
      sku: string;
      pricing_term: PricingTerm;
      purchase_option: PurchaseOption;
      usage_quantity: string;
    },
  ) =>
    request<SKUSelection>(`/connectors/${connectorId}/sku-selection`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  calculate: (architectureId: string, duration: CalculationDuration = "1_month") =>
    request<CalculationResult>(
      `/architectures/${architectureId}/calculate?duration=${duration}`,
      { method: "POST" },
    ),

  // 008-ui-updates-corrections, US5, FR-016a: prices an ad-hoc set of selections (the
  // Prior Calculation's own stored selections) at a new Duration, with no persisted
  // Architecture involved — used only for the duration-adjusted Price Change comparison.
  calculateSnapshot: (duration: CalculationDuration, selections: SnapshotSelection[]) =>
    request<CalculationResult>("/catalog/calculate-snapshot", {
      method: "POST",
      body: JSON.stringify({ duration, selections }),
    }),
};
