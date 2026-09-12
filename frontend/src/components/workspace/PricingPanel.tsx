import { AlertTriangle, Calculator, TrendingDown, TrendingUp } from "lucide-react";

import type { CalculationDuration, CalculationResult } from "../../api/client";
import { Button } from "../ui/button";
import { Separator } from "../ui/separator";
import { ErrorMessage } from "../ErrorMessage";

/** Round a decimal string (as every price in `CalculationResult` is serialized) to exactly
 * 2 decimal places for display (FR-014) — display-only; the underlying Decimal value and
 * every calculation stay full-precision (spec Assumptions). Falls back to the raw string
 * for anything that doesn't parse as a finite number, rather than showing "NaN".
 *
 * 009-ui-fixes-next-iteration, US6, FR-014: also groups with comma thousand separators
 * (`toLocaleString`, native — no new dependency) — applied at every call site (total, Price
 * Change, and the per-SKU breakdown loop below) since all three share this one function. */
function formatPrice(value: string): string {
  const n = Number(value);
  return Number.isFinite(n)
    ? n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : value;
}

export interface PricingPanelProps {
  duration: CalculationDuration;
  onDurationChange: (duration: CalculationDuration) => void;
  onCalculate: () => void;
  isCalculating: boolean;
  calculation: CalculationResult | null;
  calculationError: string | null;
  onRetry: () => void;
  /** Width in pixels (FR-012/013, 008-ui-updates-corrections) — draggable and persisted by
   * `WorkspacePage`. This column has no collapsed state, unlike columns 1-3. */
  width: number;
  /** (new total − comparison total) as a decimal string, or `null` when there's nothing to
   * compare against yet (FR-015/016) — `WorkspacePage` computes this via `priceChange.ts`
   * and owns the decision of *whether* to show it at all (a duration-only or no-op
   * Calculate must leave whatever was last shown untouched, so this prop simply doesn't
   * change on those calculates rather than the panel re-deriving anything). */
  priceChange: string | null;
}

/**
 * Column 5 (007-ui-overhaul-shadcn, FR-007): duration, Calculate, and the full result — total
 * price, warnings, and unpriceable-item notices — together in one panel (research.md;
 * spec Assumptions: "calculated price" means the complete result, not just the headline
 * number).
 */
export function PricingPanel({
  duration,
  onDurationChange,
  onCalculate,
  isCalculating,
  calculation,
  calculationError,
  onRetry,
  width,
  priceChange,
}: PricingPanelProps) {
  return (
    <aside
      className="flex h-full min-w-0 shrink-0 flex-col gap-3 overflow-auto border-l border-border p-3"
      style={{ width }}
    >
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1.5 text-2xs">
          Duration
          <select
            className="rounded border border-border bg-background px-1.5 py-1 text-2xs"
            value={duration}
            onChange={(e) => onDurationChange(e.target.value as CalculationDuration)}
          >
            <option value="1_day">1 day</option>
            <option value="1_month">1 month</option>
            <option value="1_year">1 year</option>
          </select>
        </label>
        <Button onClick={onCalculate} disabled={isCalculating} size="sm">
          <Calculator /> Calculate
        </Button>
      </div>

      {calculationError && <ErrorMessage message={calculationError} onRetry={onRetry} />}

      {calculation && (
        <section aria-label="Calculation result" className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold">
            Total: {formatPrice(calculation.total_price)} {calculation.currency}
          </h3>

          {priceChange !== null && <PriceChangeIndicator amount={priceChange} />}

          {calculation.warnings.map((w) => (
            <p
              key={w.code}
              role="alert"
              className="flex items-center gap-1.5 text-2xs text-amber-700 dark:text-amber-500"
            >
              <AlertTriangle className="size-4 shrink-0" /> {w.message}
            </p>
          ))}
          {calculation.unpriceable.length > 0 && (
            <div role="alert" className="text-2xs text-destructive">
              <p className="flex items-center gap-1.5">
                <AlertTriangle className="size-4 shrink-0" /> Some SKUs could not be priced and
                are excluded from the total:
              </p>
              <ul className="list-disc pl-5">
                {calculation.unpriceable.map((u) => (
                  <li key={u.sku_selection_id}>
                    {u.service_code} / {u.sku} — {u.reason}
                    {u.components.length > 0 && <> (in {u.components.join(", ")})</>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <PricePerSkuSection calculation={calculation} />

          {/* 009-ui-fixes-next-iteration, US6, FR-015/016: replaces the removed
              "For {duration}, priced from snapshot {date}." sentence — same
              `calculation.snapshot_date` value, at the bottom of the column. */}
          <p className="text-2xs text-muted-foreground">
            Data Timestamp: {calculation.snapshot_date}
          </p>
        </section>
      )}
    </aside>
  );
}

/** Red up-arrow when the new total is higher, green down-arrow when lower, no icon at all
 * when unchanged (FR-015). */
function PriceChangeIndicator({ amount }: { amount: string }) {
  const n = Number(amount);
  const isIncrease = n > 0;
  const isDecrease = n < 0;
  const sign = isIncrease ? "+" : "";

  return (
    <p
      className={`flex items-center gap-1.5 text-2xs ${
        isIncrease
          ? "text-red-600 dark:text-red-500"
          : isDecrease
            ? "text-green-600 dark:text-green-500"
            : "text-muted-foreground"
      }`}
    >
      {isIncrease && <TrendingUp className="size-4 shrink-0" />}
      {isDecrease && <TrendingDown className="size-4 shrink-0" />}
      Price Change: {sign}
      {formatPrice(amount)}
    </p>
  );
}

/** FR-017: every priced (non-excluded) SKU together with its own total, sorted highest-first
 * so the biggest cost driver is always at the top (Clarifications) — a view over
 * `CalculationResult.line_items` the backend already returns, no new field needed. */
function PricePerSkuSection({ calculation }: { calculation: CalculationResult }) {
  const priced = calculation.line_items
    .filter((item) => item.priceable && item.price !== null)
    .sort((a, b) => Number(b.price) - Number(a.price));

  if (priced.length === 0) return null;

  return (
    <>
      <Separator />
      <section aria-label="Price per Sku" className="flex flex-col gap-1.5">
        <h4 className="text-2xs font-semibold">Price per Sku</h4>
        <ul className="flex flex-col gap-1">
          {priced.map((item) => (
            <li
              key={item.sku_selection_id}
              className="flex items-center justify-between gap-2 text-2xs"
            >
              <span className="truncate">
                {item.service_code} / {item.sku}
              </span>
              <span className="shrink-0 tabular-nums">{formatPrice(item.price!)}</span>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
