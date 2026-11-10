/**
 * Service icon resolution for every provider (020, FR-006–FR-012, data-model §5) — the one
 * entry point the architecture diagram calls. AWS delegates to `resolveAwsServiceIcon`,
 * unchanged (FR-012). GCP and Azure resolve from their own generated, reviewed maps
 * (`{gcp,azure}ServiceIcons.generated.ts`, `backend/scripts/generate_provider_service_icon_map.py`)
 * in this order:
 *
 * 1. the first matching more specific icon for the service (FR-008a): a taxonomy prefix of the
 *    product family for GCP, a case-insensitive product-name pattern for Azure;
 * 2. the service's own icon;
 * 3. the fallback tile: the provider's logo plus a name (FR-009), never an AWS icon.
 */

import azureLogo from "../assets/providers/azure_icon.png";
import gcpLogo from "../assets/providers/gcp_icon.png";
import type { ProviderCode } from "../api/client";
import {
  AZURE_SERVICE_ICON_BY_ID,
  AZURE_SERVICE_ICON_OVERRIDES,
} from "./azureServiceIcons.generated";
import { resolveAwsServiceIcon, type ResolvedServiceIcon } from "./awsServiceIcons";
import { GCP_SERVICE_ICON_BY_ID, GCP_SERVICE_ICON_OVERRIDES } from "./gcpServiceIcons.generated";

/** The fields of a selection icon resolution reads. */
export interface IconSelection {
  service_code: string;
  product_family?: string | null;
  service_name?: string | null;
}

export type ServiceIconResult =
  | ({ kind: "icon" } & ResolvedServiceIcon)
  | { kind: "fallback"; provider: "gcp" | "azure"; name: string; logoUrl: string };

export interface ProviderIconMaps {
  byId: Readonly<Record<string, string>>;
  overrides: Readonly<Record<string, ReadonlyArray<{ match: string; icon: string }>>>;
  urlByStem: Readonly<Record<string, string>>;
  logoUrl: string;
}

function urlsByStem(glob: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(glob).map(([path, url]) => [
      path.replace(/^.*\//, "").replace(/\.svg$/, ""),
      url,
    ]),
  );
}

/** Every shipped icon, as its own hashed asset URL (loaded on demand, not inlined). */
const GCP_MAPS: ProviderIconMaps = {
  byId: GCP_SERVICE_ICON_BY_ID,
  overrides: GCP_SERVICE_ICON_OVERRIDES,
  urlByStem: urlsByStem(
    import.meta.glob<string>("../assets/gcp-icons/*.svg", {
      eager: true,
      query: "?url",
      import: "default",
    }),
  ),
  logoUrl: gcpLogo,
};

const AZURE_MAPS: ProviderIconMaps = {
  byId: AZURE_SERVICE_ICON_BY_ID,
  overrides: AZURE_SERVICE_ICON_OVERRIDES,
  urlByStem: urlsByStem(
    import.meta.glob<string>("../assets/azure-icons/*.svg", {
      eager: true,
      query: "?url",
      import: "default",
    }),
  ),
  logoUrl: azureLogo,
};

function familyMatches(provider: "gcp" | "azure", match: string, family: string): boolean {
  if (provider === "gcp") return family === match || family.startsWith(`${match} > `);
  try {
    return new RegExp(match, "i").test(family);
  } catch {
    return false;
  }
}

/** The pure resolution, given one provider's maps (exported for tests). */
export function resolveFromMaps(
  provider: "gcp" | "azure",
  selection: IconSelection,
  maps: ProviderIconMaps,
): ServiceIconResult {
  const family = selection.product_family ?? "";
  const override = family
    ? maps.overrides[selection.service_code]?.find((o) => familyMatches(provider, o.match, family))
    : undefined;
  for (const stem of [override?.icon, maps.byId[selection.service_code]]) {
    const url = stem ? maps.urlByStem[stem] : undefined;
    if (url) return { kind: "icon", lightUrl: url, darkUrl: url, isFallback: false };
  }
  const name = selection.service_name || selection.product_family || selection.service_code;
  return { kind: "fallback", provider, name, logoUrl: maps.logoUrl };
}

/** The icon (or fallback tile) for one selection on an architecture of `provider`. */
export function resolveServiceIcon(
  provider: ProviderCode,
  selection: IconSelection,
): ServiceIconResult {
  if (provider === "gcp") return resolveFromMaps("gcp", selection, GCP_MAPS);
  if (provider === "azure") return resolveFromMaps("azure", selection, AZURE_MAPS);
  return {
    kind: "icon",
    ...resolveAwsServiceIcon(selection.service_code, selection.product_family),
  };
}
