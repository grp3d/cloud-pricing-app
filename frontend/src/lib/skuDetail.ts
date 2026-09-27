/**
 * Shared candidate-key logic for a short, identifying detail summary from a SKU's attributes
 * (003-service-selection-improvements FR-001; 004-canvas-pricing-improvements FR-014). A
 * handful of common attribute keys, not a dump — so similar SKUs (e.g. several EC2 instance
 * types) can be told apart at a glance, whether in a compact search-result row or a canvas box's
 * service list. This list is a frontend display choice, not a backend contract: adding another
 * common key later doesn't require an API change. Extracted from `CatalogSearchPanel.tsx` so the
 * canvas node renderers reuse the exact same logic (004, research.md #6/DRY).
 */
const DETAIL_CANDIDATE_KEYS = [
  "instanceType",
  "memory",
  "vcpu",
  "operatingSystem",
  "storage",
  "group",
  "groupDescription",
];

/** A short " · "-joined summary from whichever candidate keys are present in `attributes`.
 * `""` when none match — callers render nothing rather than an empty separator.
 * `exclude` (016-canvas-icon-layout, FR-011) leaves out keys a caller shows elsewhere — the
 * canvas pop-up gives some attributes their own labeled line, so they aren't repeated here. */
export function summarizeAttributes(
  attributes: Record<string, string>,
  options: { exclude?: readonly string[] } = {},
): string {
  const excluded = new Set(options.exclude ?? []);
  const parts = DETAIL_CANDIDATE_KEYS.filter((key) => attributes[key] && !excluded.has(key)).map(
    (key) => attributes[key],
  );
  return parts.join(" · ");
}
