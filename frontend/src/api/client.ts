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
export type Region = components["schemas"]["RegionOut"];
export type CurrentUser = components["schemas"]["CurrentUserOut"];
export type AdminUser = components["schemas"]["AdminUserOut"];
export type ImportableArchitectures = components["schemas"]["ImportableArchitecturesOut"];
export type ArchitectureExportFile = components["schemas"]["ArchitectureExportFile"];
export type ArchitectureFileImportResponse =
  components["schemas"]["ArchitectureFileImportResponse"];
export type ImportResult = components["schemas"]["ImportResult"];
export type SystemInfo = components["schemas"]["SystemInfoOut"];

const BASE = "/api/v1";

/** The Admin import file as a whole isn't an architecture export (014, FR-019) — the server's
 * own 400 `invalid_import_file`; nothing was imported. */
export class InvalidImportFileError extends Error {}

/** The permanent per-browser guest identity (unchanged since 001) — the fallback every fresh
 * browser starts as (spec FR-015), and what "change user" → guest reverts to. Never
 * overwritten once created. */
function getGuestId(): string {
  const key = "cloud-pricing-guest-id";
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(key, id);
  }
  return id;
}

/** The bearer token actually sent on every request — the browser's "current identity"
 * (012-user-accounts-sharing, research.md §3). Defaults to the permanent guest id; overwritten
 * with a named user's id on login, and persists across reloads/restarts via `localStorage`
 * itself (FR-019a) — no separate expiry/session logic needed. */
function getCurrentIdentityId(): string {
  const key = "cloud-pricing-current-identity-id";
  let id = localStorage.getItem(key);
  if (!id) {
    id = getGuestId();
    localStorage.setItem(key, id);
  }
  return id;
}

function setCurrentIdentityId(id: string): void {
  localStorage.setItem("cloud-pricing-current-identity-id", id);
}

/** Raised when the pricing data source itself is unavailable (HTTP 503) — kept structurally
 * distinct from an empty/"no results" response so the UI never conflates the two. */
export class PricingDataUnavailableError extends Error {}

/** Raised when a catalog search field's regex pattern is malformed (008-ui-updates-
 * corrections, FR-021, contracts/api.md) — `field` names which of `service_code`/
 * `product_family`/`text`/`from_region_code`/`to_region_code` (the latter two added
 * 009-ui-fixes-next-iteration, US9) the bad pattern came from, so the caller can show the
 * message inline next to that field rather than as a generic banner. */
export class InvalidRegexPatternError extends Error {
  field: "service_code" | "product_family" | "text" | "from_region_code" | "to_region_code";

  constructor(
    message: string,
    field: "service_code" | "product_family" | "text" | "from_region_code" | "to_region_code",
  ) {
    super(message);
    this.field = field;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getCurrentIdentityId()}`,
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
    if (body.error === "invalid_import_file") {
      throw new InvalidImportFileError(body.message ?? "the file is not in the expected format");
    }
    if (body.error === "invalid_regex_pattern") {
      throw new InvalidRegexPatternError(body.message ?? "Invalid pattern.", body.field);
    }
    // 010-multi-region-support, spec FR-004: the server-side region-match gate on
    // PATCH /collections/{id} returns a structured `detail` object, not a plain string —
    // build a readable message from it rather than stringifying the object.
    if (body.detail && typeof body.detail === "object" && body.detail.error === "region_mismatch") {
      throw new Error(
        `This Application is in ${body.detail.application_region}, but that VPC is in ` +
          `${body.detail.vpc_region} — they must match to nest.`,
      );
    }
    throw new Error(body.detail ?? body.message ?? `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listProviders: () => request<Provider[]>("/providers"),

  // --- Identity/auth (012-user-accounts-sharing) ---
  getCurrentUser: () => request<CurrentUser>("/auth/me"),
  checkUsername: (username: string) =>
    request<{ exists: boolean; has_password: boolean }>("/auth/check-username", {
      method: "POST",
      body: JSON.stringify({ username }),
    }),
  /** Also sets the account's password on first use (FR-017) — the server, not the client,
   * decides which case applies. On success, updates the browser's current identity. */
  login: async (username: string, password: string) => {
    const user = await request<CurrentUser>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setCurrentIdentityId(user.id);
    return user;
  },

  // --- Admin system information (016-canvas-icon-layout, US5) ---
  getSystemInfo: () => request<SystemInfo>("/admin/system-info"),
  /** 018-app-cloud-deployment, FR-012: run one pricing-snapshot check now. */
  startSnapshotCheck: async () => {
    const res = await fetch(`${BASE}/admin/pricing-snapshot/check`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getCurrentIdentityId()}` },
    });
    if (res.status === 409) throw new Error("A check is already running.");
    if (!res.ok) throw new Error(`Could not start a check: ${res.status}`);
    return (await res.json()) as components["schemas"]["SnapshotCheckStartedOut"];
  },

  // --- Admin user management (012-user-accounts-sharing) ---
  listAdminUsers: () => request<AdminUser[]>("/admin/users"),
  createAdminUser: (username: string) =>
    request<AdminUser>("/admin/users", { method: "POST", body: JSON.stringify({ username }) }),
  setAdminUserActive: (id: string, isActive: boolean) =>
    request<AdminUser>(`/admin/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: isActive }),
    }),
  setAdminUserPassword: (id: string, password: string) =>
    request<AdminUser>(`/admin/users/${id}/password`, {
      method: "PUT",
      body: JSON.stringify({ password }),
    }),
  deleteAdminUser: (id: string) => request<void>(`/admin/users/${id}`, { method: "DELETE" }),
  /** All of one user's architectures in the export format (014, FR-015/FR-017). */
  exportUserArchitectures: (userId: string) =>
    request<ArchitectureExportFile>(`/admin/users/${userId}/architectures/export`),
  /** Import a parsed export file into one user's account (014, FR-018-FR-023). */
  importUserArchitectures: (userId: string, doc: unknown) =>
    request<ArchitectureFileImportResponse>(`/admin/users/${userId}/architectures/import`, {
      method: "POST",
      body: JSON.stringify(doc),
    }),

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
  /** Owner-only public/private toggle (012-user-accounts-sharing, spec FR-020). */
  setArchitecturePublic: (id: string, isPublic: boolean) =>
    request<ArchitectureSummary>(`/architectures/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_public: isPublic }),
    }),
  /** Every other user's public architectures, pre-grouped/sorted server-side (FR-023-026). */
  listImportableArchitectures: () =>
    request<ImportableArchitectures>("/architectures/importable"),
  /** Deep-copies a public architecture into the caller's own list under `name` (FR-028/029). */
  importArchitecture: (architectureId: string, name: string) =>
    request<ArchitectureSummary>(`/architectures/${architectureId}/import`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  /** 010-multi-region-support, spec FR-001/FR-001a: `region` is required unless
   * `parentCollectionId` is given, in which case the server ignores it and inherits the
   * parent VPC's region instead. */
  createCollection: (
    architectureId: string,
    type: CollectionType,
    name: string,
    region?: string,
    parentCollectionId?: string,
  ) =>
    request<Collection>(`/architectures/${architectureId}/collections`, {
      method: "POST",
      body: JSON.stringify({
        type,
        name,
        region,
        parent_collection_id: parentCollectionId,
      }),
    }),
  deleteCollection: (id: string) => request<void>(`/collections/${id}`, { method: "DELETE" }),
  /** Nest, move, or un-nest an Application Component (002-vpc-component-nesting, FR-001-003).
   * Pass a VPC's id to nest/move into it, or `null` to un-nest back to top-level. May reject
   * with a `409` region-mismatch (010-multi-region-support, spec FR-004). */
  updateCollectionParent: (id: string, parentCollectionId: string | null) =>
    request<Collection>(`/collections/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ parent_collection_id: parentCollectionId }),
    }),
  /** Change a collection's region while it's still unlocked (010-multi-region-support, spec
   * FR-003) — `409` once it has content. */
  updateCollectionRegion: (id: string, region: string) =>
    request<Collection>(`/collections/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ region }),
    }),

  /** Regions the pricing dataset currently has data for (010-multi-region-support, FR-017). */
  listRegions: () => request<{ regions: Region[] }>("/regions"),

  searchCatalog: (params: {
    region: string;
    service_code?: string;
    product_family?: string;
    q?: string;
    from_region_code?: string;
    to_region_code?: string;
  }) => {
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
      /** 016-canvas-icon-layout, FR-004a: move the service to another box (same region). */
      collection_id: string;
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
