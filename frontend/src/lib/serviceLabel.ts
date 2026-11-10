/**
 * 021 US7 (FR-044 to FR-047): one readable label for a service, shared by the canvas hover
 * text, the Service tab and the Price per SKU list.
 *
 * GCP and Azure codes are opaque ("95FF-2EF5-5EA1 / EE2C-E844-D760"), so a service with a
 * provider name or description is shown by those, with the codes kept as a muted line. AWS
 * services carry neither (their readable details are AWS attributes), so they keep today's
 * display.
 */
export interface ServiceLabelSource {
  service_code: string;
  sku: string;
  service_name?: string | null;
  summary?: string | null;
}

export interface ServiceLabel {
  /** The provider's service name, or the service code when there is none. */
  name: string;
  /** The item's own description, when it has one that isn't just the name. */
  description: string | null;
  /** "service_code / sku", shown muted beside the readable label. */
  codes: string;
  /** Whether `name` or `description` is readable text rather than codes. */
  readable: boolean;
}

export function serviceLabel(s: ServiceLabelSource): ServiceLabel {
  const serviceName = s.service_name?.trim() || null;
  const summary = s.summary?.trim() || null;
  const name = serviceName ?? s.service_code;
  return {
    name,
    description: summary && summary !== name ? summary : null,
    codes: `${s.service_code} / ${s.sku}`,
    readable: Boolean(serviceName || summary),
  };
}

/** The name and description on one line, e.g. "Cloud Storage — Multi-Region … Operations". */
export function serviceLabelText(label: ServiceLabel): string {
  return label.description ? `${label.name} — ${label.description}` : label.name;
}
