/**
 * Which of the two proration interpretations a usage-quantity value represents, so the pricing
 * inputs form can tell the user which one it's asking for (004-canvas-pricing-improvements,
 * FR-007). Mirrors the classification `backend/src/pricing_data/duration.py`'s `classify_unit()`
 * already computes for the *real pricing math* — this copy exists only to choose a label, never
 * to compute a price, so a small, independently-maintained frontend table (matching the
 * `nodeLayout.ts`/`dropTargetDetection.ts` precedent of pure, testable decision functions) is a
 * deliberately lighter-weight duplication than adding a new API field just for a hint.
 *
 * A function of `unit` alone (006-fix-reserved-pricing dropped the `term` parameter this used
 * to take): usage_quantity has no Reserved-term meaning at all now, so `PricingInputsForm`
 * never renders — and never needs a hint for — the input once a Reserved term is selected
 * (FR-007); this function is only ever called for an On-Demand selection's unit.
 */

// Same set backend/src/pricing_data/duration.py's `_NO_PERIOD_UNITS` recognizes (FR-003).
const NO_PERIOD_UNITS = new Set([
  "Hrs",
  "Hours",
  "hours",
  "hour",
  "Hour",
  "Hourly",
  "Instance-hrs",
  "usagehours",
  "vCPU-Hours",
  "seconds",
  "Minute",
  "minutes",
  "minute",
  "callme-minutes",
  "Requests",
  "Request",
  "API Request",
  "GB",
  "1K tokens",
  "1M tokens",
  "Transformations",
  "Messages",
  "Images Processed",
  "Tasks",
  "Pages",
  "Count",
  "Unit",
  "Units",
  "sms-message",
  "Position",
  "image",
]);

// Same set backend/src/pricing_data/duration.py's `_FIXED_PERIOD_UNITS` recognizes (FR-004).
const FIXED_PERIOD_UNITS = new Set([
  "Months",
  "Month",
  "GB-Mo",
  "GB-month",
  "vCPU-Months",
  "IOPS-Mo",
  "MBPS-Mo",
]);

export type UsageQuantityHint = "per_day_estimate" | "period_denominated" | null;

/**
 * `"per_day_estimate"`: the quantity is a steady daily rate the selected Calculate duration
 * scales up (FR-003). `"period_denominated"`: the quantity is an already-period-denominated
 * unit's own quantity — not scaled the same way (FR-004). `null`: no clear hint (no unit yet,
 * or a unit not recognized by either table — that SKU would be excluded from a duration-scoped
 * total per FR-005, so no hint would be actionable anyway).
 */
export function usageQuantityHint(unit: string | null | undefined): UsageQuantityHint {
  if (!unit) return null;
  if (NO_PERIOD_UNITS.has(unit)) return "per_day_estimate";
  if (FIXED_PERIOD_UNITS.has(unit)) return "period_denominated";
  return null;
}
