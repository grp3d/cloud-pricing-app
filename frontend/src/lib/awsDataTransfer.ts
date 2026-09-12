/**
 * Derived display label for `AWSDataTransfer` SKUs (009-ui-fixes-next-iteration, US9,
 * FR-027/028/030, data-model.md, research.md §9) — a small, pure, easily-unit-tested helper
 * alongside the existing `skuDetail.ts` sibling it complements. `fromRegionCode`/
 * `toRegionCode` already live inside every SKU's `attributes` (the API's existing
 * `parse_attributes()`/`json_extract_string` flattening, no new backend field) — this module
 * only derives a presentational label from them, never fabricating a value that isn't there
 * (Constitution Principle I).
 */

/** Returns the derived "{fromRegionCode}=>{toRegionCode}" label for an AWSDataTransfer SKU, or
 * `null` when `serviceCode` isn't `AWSDataTransfer`, or either region field is absent (missing
 * key or empty string — research.md §9's real-data shape for internet/CloudFront-bound
 * transfers) from `attributes`. Callers fall back to their own existing default label whenever
 * this returns `null`. */
export function awsDataTransferLabel(
  serviceCode: string,
  attributes: Record<string, string>,
): string | null {
  if (serviceCode !== "AWSDataTransfer") return null;
  const { fromRegionCode, toRegionCode } = attributes;
  if (!fromRegionCode || !toRegionCode) return null;
  return `${fromRegionCode}=>${toRegionCode}`;
}
