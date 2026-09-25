/**
 * Content of a canvas service icon's hover/focus pop-up (015-canvas-service-icons, FR-008-
 * FR-012, data-model.md §3) — the details the old single `service_code / sku — detail` text row
 * carried, now one labeled line each. Pure, so the pop-up, the icon's accessible name, and the
 * unit tests all share one definition. Reuses the canvas's existing identifying-detail summary
 * (`skuDetail.ts`) and data-transfer region-pair label (`awsDataTransfer.ts`) rather than
 * re-deriving either; lines whose value is missing are omitted, never shown empty (FR-009).
 */

import type { SKUSelection } from "../api/client";
import { awsDataTransferLabel } from "./awsDataTransfer";
import { summarizeAttributes } from "./skuDetail";

/** The pop-up's lines, in order: service code; `Sku:`; the data-transfer region pair (data
 * transfer only, FR-010); the identifying-detail summary; `UsageType:`; `Operation:`. */
export function buildServicePopupLines(
  selection: Pick<SKUSelection, "service_code" | "sku" | "attributes">,
): string[] {
  const { service_code, sku, attributes } = selection;
  const lines = [service_code, `Sku: ${sku}`];

  const regionPair = awsDataTransferLabel(service_code, attributes);
  if (regionPair) lines.push(regionPair);

  const summary = summarizeAttributes(attributes);
  if (summary) lines.push(summary);

  if (attributes.usagetype) lines.push(`UsageType: ${attributes.usagetype}`);
  if (attributes.operation) lines.push(`Operation: ${attributes.operation}`);
  return lines;
}

/** The icon's accessible name — the same content as the pop-up, on one line (FR-012). */
export function servicePopupAccessibleName(lines: string[]): string {
  return lines.join(", ");
}
