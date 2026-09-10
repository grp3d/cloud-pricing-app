import { AlertTriangle, Calculator } from "lucide-react";

import type { CalculationDuration, CalculationResult } from "../../api/client";
import { Button } from "../ui/button";
import { ErrorMessage } from "../ErrorMessage";

export interface PricingPanelProps {
  duration: CalculationDuration;
  onDurationChange: (duration: CalculationDuration) => void;
  onCalculate: () => void;
  isCalculating: boolean;
  calculation: CalculationResult | null;
  calculationError: string | null;
  onRetry: () => void;
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
}: PricingPanelProps) {
  return (
    <aside className="flex h-full w-72 min-w-0 shrink-0 flex-col gap-3 overflow-auto border-l border-border p-3">
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1.5 text-sm">
          Duration
          <select
            className="rounded border border-border bg-background px-1.5 py-1 text-sm"
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
          <h3 className="text-base font-semibold">
            Total: {calculation.total_price} {calculation.currency}
          </h3>
          <p className="text-xs text-muted-foreground">
            For {calculation.duration.replace("_", " ")}, priced from snapshot{" "}
            {calculation.snapshot_date}.
          </p>
          {calculation.warnings.map((w) => (
            <p
              key={w.code}
              role="alert"
              className="flex items-center gap-1.5 text-sm text-amber-700 dark:text-amber-500"
            >
              <AlertTriangle className="size-4 shrink-0" /> {w.message}
            </p>
          ))}
          {calculation.unpriceable.length > 0 && (
            <div role="alert" className="text-sm text-destructive">
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
        </section>
      )}
    </aside>
  );
}
