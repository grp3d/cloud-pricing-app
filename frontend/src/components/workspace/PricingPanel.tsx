import { AlertTriangle, Calculator, TrendingDown, TrendingUp, WrapText } from "lucide-react";
import { useState } from "react";

import type { CalculationDuration, CalculationResult } from "../../api/client";
import { useMeasuredWidth } from "../../hooks/useMeasuredWidth";
import { awsDataTransferLabel } from "../../lib/awsDataTransfer";
import { splitForWrap } from "../../lib/textWrap";
import { Button } from "../ui/button";
import { Separator } from "../ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import { ErrorMessage } from "../ErrorMessage";

/** A single shared `<canvas>` for `measureTextWidth` below — created lazily on first use,
 * reused for every measurement rather than one canvas per call. */
let measureCanvas: HTMLCanvasElement | null = null;

/** Renders-width of `text` in `font` (a CSS `font` shorthand string), via `CanvasRenderingContext2D.measureText` — the
 * one reliable way to know a string's pixel width ahead of layout, matching what the browser's
 * own text rendering will actually produce (unlike an average-character-width guess). Falls
 * back to a rough character-count estimate on the (real-browser-only; never happens in
 * practice) chance `getContext("2d")` returns `null`, rather than throwing. */
function measureTextWidth(text: string, font: string): number {
  if (!measureCanvas) measureCanvas = document.createElement("canvas");
  const ctx = measureCanvas.getContext("2d");
  if (!ctx) return text.length * 6;
  ctx.font = font;
  return ctx.measureText(text).width;
}

/** The `text-2xs` token's rendered `font` shorthand (`lib/index.css`'s `--text-2xs`/
 * `--font-sans`) — every Price per Sku line uses exactly this class with no per-row override,
 * so this is computed from the *root* font-size (correct even when a user's browser default
 * font size isn't the usual 16px — an accessibility setting `splitForWrap`'s accuracy
 * shouldn't silently ignore) rather than a flat hardcoded pixel value. */
function priceLineFont(): string {
  const rootPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  return `${rootPx * 0.6875}px 'Geist Variable', sans-serif`;
}

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
  /** 009-ui-fixes-next-iteration, US9, FR-028: each SKU Selection's `attributes`, by id —
   * `CalculationResult.line_items` doesn't carry `attributes` itself (contracts/api.md §2:
   * response shape unchanged), so `WorkspacePage` re-shapes its own `skuSelectionsById` map
   * for the per-SKU breakdown below to derive the AWSDataTransfer label from. */
  skuAttributesById: Map<string, Record<string, string>>;
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
  skuAttributesById,
}: PricingPanelProps) {
  // 009-ui-fixes-next-iteration follow-up: word-wrap for the Price per Sku list, off by
  // default (unchanged from today's single-line-truncated behavior) — in-session only, not
  // persisted (not asked for, unlike 1a/1b's column-collapse/diagram-zoom state).
  const [wordWrap, setWordWrap] = useState(false);

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

          <PricePerSkuSection
            calculation={calculation}
            skuAttributesById={skuAttributesById}
            wordWrap={wordWrap}
          />

          {/* 009-ui-fixes-next-iteration, US6, FR-015/016: replaces the removed
              "For {duration}, priced from snapshot {date}." sentence — same
              `calculation.snapshot_date` value, at the bottom of the column. */}
          <p className="text-2xs text-muted-foreground">
            Data Timestamp: {calculation.snapshot_date}
          </p>

          {/* 009-ui-fixes-next-iteration follow-up: word-wrap toggle for the Price per Sku
              list above — bottom-left of the column, under the Data Timestamp line. */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={wordWrap ? "secondary" : "ghost"}
                size="icon-sm"
                aria-label={
                  wordWrap
                    ? "Disable word wrap for Price per Sku"
                    : "Enable word wrap for Price per Sku"
                }
                aria-pressed={wordWrap}
                onClick={() => setWordWrap((v) => !v)}
                className="self-start"
              >
                <WrapText />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{wordWrap ? "Disable word wrap" : "Enable word wrap"}</TooltipContent>
          </Tooltip>
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
function PricePerSkuSection({
  calculation,
  skuAttributesById,
  wordWrap,
}: {
  calculation: CalculationResult;
  skuAttributesById: Map<string, Record<string, string>>;
  /** 009-ui-fixes-next-iteration follow-up: when off (default), each line behaves exactly as
   * it always has — single line, CSS-truncated with an ellipsis. When on, `PriceLine` below
   * keeps that same first-line shape but also shows whatever didn't fit, on a second,
   * indented line, instead of discarding it. */
  wordWrap: boolean;
}) {
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
          {priced.map((item) => {
            // 009-ui-fixes-next-iteration, US9, FR-027/028: the derived region-pair label
            // replaces the raw SKU here for AWSDataTransfer Services; every other Service is
            // unaffected (FR-030) since this is `null` for them.
            const dataTransferLabel = awsDataTransferLabel(
              item.service_code,
              skuAttributesById.get(item.sku_selection_id) ?? {},
            );
            return (
              <PriceLine
                key={item.sku_selection_id}
                text={`${item.service_code} / ${dataTransferLabel ?? item.sku}`}
                price={formatPrice(item.price!)}
                wordWrap={wordWrap}
              />
            );
          })}
        </ul>
      </section>
    </>
  );
}

/** One Price per Sku row (FR-017's list item, split out of `PricePerSkuSection` for its own
 * `wordWrap`-driven measurement). `wordWrap` off: unchanged from today — a single
 * CSS-truncated line via `useMeasuredWidth`'s ref only enabling the *next* toggle-on to
 * already know the right width, not for any visual effect itself. `wordWrap` on: the same
 * first line (ellipsis included, from `splitForWrap`), plus a second, `pl-[2ch]`-indented
 * line for whatever didn't fit — indented so it reads as this line's own continuation, not a
 * new list item, per the explicit ask. */
function PriceLine({
  text,
  price,
  wordWrap,
}: {
  text: string;
  price: string;
  wordWrap: boolean;
}) {
  const [labelRef, labelWidth] = useMeasuredWidth<HTMLSpanElement>();

  const { firstLine, remainder } =
    wordWrap && labelWidth !== null
      ? splitForWrap(text, labelWidth, (s) => measureTextWidth(s, priceLineFont()))
      : { firstLine: text, remainder: null };

  return (
    <li className="flex flex-col gap-0.5 text-2xs">
      <div className="flex items-center justify-between gap-2">
        <span ref={labelRef} className={wordWrap ? "min-w-0 flex-1" : "min-w-0 flex-1 truncate"}>
          {wordWrap ? firstLine : text}
        </span>
        <span className="shrink-0 tabular-nums">{price}</span>
      </div>
      {wordWrap && remainder !== null && <p className="pl-[2ch]">{remainder}</p>}
    </li>
  );
}
