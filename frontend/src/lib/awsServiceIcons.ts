/**
 * AWS service icon resolution for the architecture canvas (015-canvas-service-icons, FR-002/
 * FR-003/FR-004, data-model.md §2). The mapping itself is static, reviewed data generated from
 * the real pricing service codes and the official AWS icon package
 * (`awsServiceIcons.generated.ts`, `backend/scripts/generate_aws_service_icon_map.py`) — this
 * module only turns a service code (plus its product family, when an override exists) into a
 * shippable icon URL, deterministically, with a single fallback for anything unmatched.
 *
 * AWS-specific by name, like `awsDataTransfer.ts`: another provider would add a sibling
 * resolver rather than extend this one (Constitution Principle III).
 */

import {
  AWS_DATA_TRANSFER_ICON,
  AWS_FALLBACK_ICON,
  AWS_SERVICE_ICON_BY_CODE,
  AWS_SERVICE_ICON_BY_CODE_AND_FAMILY,
} from "./awsServiceIcons.generated";

/** Every shipped icon, as its own hashed asset URL (loaded on demand, not inlined). */
const ICON_URL_BY_STEM: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>("../assets/aws-icons/*.svg", {
      eager: true,
      query: "?url",
      import: "default",
    }),
  ).map(([path, url]) => [path.replace(/^.*\//, "").replace(/\.svg$/, ""), url]),
);

export interface ResolvedServiceIcon {
  /** URL to render in light theme. */
  lightUrl: string;
  /** URL to render in dark theme — equal to `lightUrl` for ordinary service icons. */
  darkUrl: string;
  /** True when no icon matched and the generic AWS fallback is used (FR-004). */
  isFallback: boolean;
}

function single(stem: string): ResolvedServiceIcon {
  const url = ICON_URL_BY_STEM[stem];
  return { lightUrl: url, darkUrl: url, isFallback: false };
}

function themed(icon: { light: string; dark: string }, isFallback: boolean): ResolvedServiceIcon {
  return {
    lightUrl: ICON_URL_BY_STEM[icon.light],
    darkUrl: ICON_URL_BY_STEM[icon.dark],
    isFallback,
  };
}

/** The icon for one service, in data-model.md §2's resolution order: product-family override,
 * then AWSDataTransfer's Data Stream icon, then the service-code icon, then the fallback. */
export function resolveAwsServiceIcon(
  serviceCode: string,
  productFamily: string | null | undefined,
): ResolvedServiceIcon {
  const familyStem = productFamily
    ? AWS_SERVICE_ICON_BY_CODE_AND_FAMILY[serviceCode]?.[productFamily]
    : undefined;
  if (familyStem && ICON_URL_BY_STEM[familyStem]) return single(familyStem);

  if (serviceCode === "AWSDataTransfer") return themed(AWS_DATA_TRANSFER_ICON, false);

  const codeStem = AWS_SERVICE_ICON_BY_CODE[serviceCode];
  if (codeStem && ICON_URL_BY_STEM[codeStem]) return single(codeStem);

  return themed(AWS_FALLBACK_ICON, true);
}
