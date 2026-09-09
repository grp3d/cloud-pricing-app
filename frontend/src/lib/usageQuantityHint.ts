import type { PricingTerm } from "../api/client";

/**
 * Which of the two proration interpretations a usage-quantity value represents, so the pricing
 * inputs form can tell the user which one it's asking for (004-canvas-pricing-improvements,
 * FR-007). Mirrors the classification `backend/src/pricing_data/duration.py`'s `classify_unit()`
 * already computes for the *real pricing math* — this copy exists only to choose a label, never
 * to compute a price, so a small, independently-maintained frontend table (matching the
 * `nodeLayout.ts`/`dropTargetDetection.ts` precedent of pure, testable decision functions) is a
 * deliberately lighter-weight duplication than adding a new API field just for a hint (see
 * PricingInputsForm.tsx's Reserved-vs-on-demand half of this decision, which is live form state
 * that couldn't come from a static API field anyway).
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
 * scales up (FR-003). `"period_denominated"`: the quantity is the SKU's own quantity for a
 * Reserved commitment or an already-period-denominated unit — not scaled the same way (FR-004,
 * or any Reserved term). `null`: no clear hint (no unit yet, or a unit not recognized by either
 * table — that SKU would be excluded from a duration-scoped total per FR-005, so no hint would
 * be actionable anyway).
 */
export function usageQuantityHint(
  term: PricingTerm,
  unit: string | null | undefined,
): UsageQuantityHint {
  if (!unit) return null;
  if (term !== "on_demand") return "period_denominated";
  if (NO_PERIOD_UNITS.has(unit)) return "per_day_estimate";
  if (FIXED_PERIOD_UNITS.has(unit)) return "period_denominated";
  return null;
}
