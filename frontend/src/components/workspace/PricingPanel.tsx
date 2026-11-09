import { AlertTriangle, Calculator, TrendingDown, TrendingUp, WrapText } from "lucide-react";
import { useState } from "react";

import type { CalculationDuration, CalculationResult, PriceLineItem } from "../../api/client";
import { useMeasuredWidth } from "../../hooks/useMeasuredWidth";
import { awsDataTransferLabel } from "../../lib/awsDataTransfer";
import { groupLineItemsByRegion } from "../../lib/regionPricingGroups";
import { type ServiceLabel, serviceLabelText } from "../../lib/serviceLabel";
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

/** A quantity or rate for the line detail: up to 6 decimals, grouped (019). */
function formatAmount(value: string): string {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString("en-US", { maximumFractionDigits: 6 }) : value;
}

/** 019 (contracts §5, FR-008): what a line's price is made of — its price type when not on
 * demand, its graduated tiers, and a GCP machine's cores and RAM. Null when there's nothing to
 * add (a plain on-demand price). */
export function LineDetail({ item }: { item: PriceLineItem }) {
  const label =
    item.price_type_label && item.price_type_label !== "On demand" ? item.price_type_label : null;
  const tiers = item.tiers ?? [];
  const components = item.components ?? [];
  if (!label && tiers.length === 0 && components.length === 0) return null;
  return (
    <div className="flex flex-col gap-0.5 pl-[2ch] text-2xs text-muted-foreground">
      {label && <p>{label}</p>}
      {tiers.length > 0 && (
        <ul aria-label="Price tiers" className="flex flex-col">
          {tiers.map((t) => (
            <li key={t.from_quantity} className="flex justify-between gap-2">
              <span>
                {formatAmount(t.from_quantity)}–{t.to_quantity ? formatAmount(t.to_quantity) : "∞"}{" "}
                at {formatAmount(t.rate)}: {formatAmount(t.quantity)}
              </span>
              <span className="tabular-nums">{formatPrice(t.cost)}</span>
            </li>
          ))}
        </ul>
      )}
      {components.length > 0 && (
        <ul aria-label="Price components" className="flex flex-col">
          {components.map((c) => (
            <li key={c.label} className="flex justify-between gap-2">
              <span>
                {c.label}: {formatAmount(c.quantity)} at {formatAmount(c.rate)}
              </span>
              <span className="tabular-nums">{formatPrice(c.cost)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export interface PricingPanelProps {
  duration: CalculationDuration;
  onDurationChange: (duration: CalculationDuration) => void;
  onCalculate: () => void;
  isCalculating: boolean;
  calculation: CalculationResult | null;
  calculationError: string | null;
  onRetry: () => void;
  /** (new total − comparison total) as a decimal string, or `null` when there's nothing to
   * compare against yet (FR-015/016) — `WorkspacePage` computes this via `priceChange.ts`
   * and owns the decision of *whether* to show it at all (a duration-only or no-op
   * Calculate must leave whatever was last shown untouched, so this prop simply doesn't
   * change on those calculates rather than the panel re-deriving anything). */
  priceChange: string | null;
  /** 020 (FR-005): Price Change can't be worked out for this calculation (a baseline stored by
   * v0.0.2 on a GCP or Azure architecture, then a Duration switch) — shown as a muted note in
   * the Price Change line's place instead of a figure. */
  priceChangeUnavailable?: boolean;
  /** 009-ui-fixes-next-iteration, US9, FR-028: each SKU Selection's `attributes`, by id —
   * `CalculationResult.line_items` doesn't carry `attributes` itself (contracts/api.md §2:
   * response shape unchanged), so `WorkspacePage` re-shapes its own `skuSelectionsById` map
   * for the per-SKU breakdown below to derive the AWSDataTransfer label from. */
  skuAttributesById: Map<string, Record<string, string>>;
  /** 021 US7 (FR-047): each SKU Selection's readable label, by id; a line without one (or with
   * an unreadable one, AWS) keeps "service_code / sku". */
  skuLabelsById?: Map<string, ServiceLabel>;
  /** 015-canvas-service-icons, FR-018a: the displayed (stored) result was calculated from
   * different services, inputs, or regions than the Architecture has now. */
  isOutOfDate: boolean;
}

/**
 * The Price Summary (007-ui-overhaul-shadcn, FR-007): duration, Calculate, and the full result
 * — total price, warnings, and unpriceable-item notices — together in one panel (research.md;
 * spec Assumptions: "calculated price" means the complete result, not just the headline
 * number). 021 (FR-013, FR-018b): the inspector's Pricing tab body; the inspector owns the
 * width and the collapse, and this body scrolls on its own.
 */
export function PricingPanel({
  duration,
  onDurationChange,
  onCalculate,
  isCalculating,
  calculation,
  calculationError,
  onRetry,
  priceChange,
  priceChangeUnavailable = false,
  skuAttributesById,
  skuLabelsById = new Map(),
  isOutOfDate,
}: PricingPanelProps) {
  // 009-ui-fixes-next-iteration follow-up: word-wrap for the Price per Sku list, off by
  // default (unchanged from today's single-line-truncated behavior) — in-session only, not
  // persisted (not asked for, unlike 1a/1b's column-collapse/diagram-zoom state).
  const [wordWrap, setWordWrap] = useState(false);

  // 021 US8 (FR-048): duration, Calculate, the total and Price Change stay pinned above a
  // divider; everything below scrolls on its own. The result region spans both parts, so the
  // total and Price Change are still read from it.
  return (
    <div
      role={calculation ? "region" : undefined}
      aria-label={calculation ? "Calculation result" : undefined}
      className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
    >
      <div data-testid="pricing-pinned" className="flex shrink-0 flex-col gap-2 px-3 pt-3">
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-2xs">
            Duration
            <select
              className="rounded-md border border-input bg-background px-1.5 py-1 text-2xs"
              value={duration}
              onChange={(e) => onDurationChange(e.target.value as CalculationDuration)}
            >
              <option value="1_day">1 day</option>
              <option value="1_month">1 month</option>
              <option value="1_year">1 year</option>
            </select>
          </label>
          {/* 021 US5 (FR-040): dark blue when there's something new to price (out of date, or
            never priced), light blue otherwise. Clickable either way. */}
          <Button
            onClick={onCalculate}
            disabled={isCalculating}
            size="sm"
            variant={isOutOfDate || !calculation ? "default" : "soft"}
          >
            <Calculator /> Calculate
          </Button>
        </div>

        {calculation && (
          <>
            {/* 021 (FR-029): equal-width digits, so a recalculated total doesn't shift sideways. */}
            <h3 className="text-xs font-semibold tabular-nums">
              Total: {formatPrice(calculation.total_price)} {calculation.currency}
            </h3>

            {priceChangeUnavailable ? (
              <p className="text-2xs text-muted-foreground">
                Not available: previous calculation from prior version is unreliable
              </p>
            ) : (
              priceChange !== null && <PriceChangeIndicator amount={priceChange} />
            )}
          </>
        )}
        <Separator />
      </div>

      <div
        data-testid="pricing-scroll"
        className="flex min-h-0 flex-1 flex-col gap-2 overflow-auto p-3"
      >
        {calculationError && <ErrorMessage message={calculationError} onRetry={onRetry} />}

        {calculation && (
          <>
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
                      {skuLabelsById.get(u.sku_selection_id)?.readable
                        ? serviceLabelText(skuLabelsById.get(u.sku_selection_id)!)
                        : `${u.service_code} / ${u.sku}`}{" "}
                      — {u.reason}
                      {u.components.length > 0 && <> (in {u.components.join(", ")})</>}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <PricePerSkuSection
              calculation={calculation}
              skuAttributesById={skuAttributesById}
              skuLabelsById={skuLabelsById}
              wordWrap={wordWrap}
              onToggleWordWrap={() => setWordWrap((v) => !v)}
            />

            {/* 009-ui-fixes-next-iteration, US6, FR-015/016: replaces the removed
              "For {duration}, priced from snapshot {date}." sentence — same
              `calculation.snapshot_date` value, at the bottom of the column.
              018-app-cloud-deployment, FR-059: a corrected revision of the same date is never
              shown under the same label — its revision follows, lighter and in parentheses. The
              first revision, by far the most common, shows the date alone. */}
            <p className="text-2xs text-muted-foreground">
              Data Timestamp: {calculation.snapshot_date}
              {calculation.snapshot_revision > 1 && (
                <span className="opacity-60"> (r{calculation.snapshot_revision})</span>
              )}
            </p>

            {/* 015-canvas-service-icons, FR-018a: a stored result is still the last calculated
              price, but no longer matches the Architecture — say so, directly under Data
              Timestamp, rather than recalculating behind the user's back. */}
            {isOutOfDate && (
              <p
                role="status"
                className="flex items-center gap-1.5 text-2xs text-amber-700 dark:text-amber-500"
              >
                <AlertTriangle className="size-4 shrink-0" /> Architecture has been updated since
                last pricing
              </p>
            )}
          </>
        )}
      </div>
    </div>
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
      className={`flex items-center gap-1.5 text-2xs tabular-nums ${
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

/** 010-multi-region-support, spec FR-011/FR-012/FR-014: every priced (non-excluded) SKU,
 * grouped into one labeled section per region (a `"Global"` section for the FR-015 defensive
 * fallback), each with a subtotal — within each section, still sorted highest-first so the
 * biggest cost driver is always at the top (Clarifications, preserved from the prior flat
 * list) — a view over `CalculationResult.line_items` the backend already returns, no new
 * field needed beyond `region`. */
function PricePerSkuSection({
  calculation,
  skuAttributesById,
  skuLabelsById,
  wordWrap,
  onToggleWordWrap,
}: {
  calculation: CalculationResult;
  skuAttributesById: Map<string, Record<string, string>>;
  skuLabelsById: Map<string, ServiceLabel>;
  /** 009-ui-fixes-next-iteration follow-up: when off (default), each line behaves exactly as
   * it always has — single line, CSS-truncated with an ellipsis. When on, `PriceLine` below
   * keeps that same first-line shape but also shows whatever didn't fit, on a second,
   * indented line, instead of discarding it. */
  wordWrap: boolean;
  onToggleWordWrap: () => void;
}) {
  const priced = calculation.line_items.filter(
    (item): item is typeof item & { price: string } => item.priceable && item.price !== null,
  );
  if (priced.length === 0) return null;

  const groups = groupLineItemsByRegion(priced);

  return (
    <>
      {/* 021 US8: the divider above this list is now the pinned one at the top of the tab. */}
      <section aria-label="Price per Sku" className="flex flex-col gap-3">
        {/* 015-canvas-service-icons, FR-023: the word-wrap toggle (009 follow-up) sits on this
            heading row, right-aligned with the prices it wraps, instead of at the very bottom
            of the column; the heading truncates rather than overlap it when narrow. */}
        <div className="flex items-center justify-between gap-2">
          <h4 className="min-w-0 truncate text-2xs font-semibold">Price per Sku</h4>
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
                onClick={onToggleWordWrap}
                className="shrink-0"
              >
                <WrapText />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{wordWrap ? "Disable word wrap" : "Enable word wrap"}</TooltipContent>
          </Tooltip>
        </div>
        {groups.map((group) => (
          <div key={group.region} className="flex flex-col gap-1.5">
            <h5 className="text-2xs font-medium text-muted-foreground">Region {group.region}</h5>
            <ul className="flex flex-col gap-1">
              {group.items.map((item) => {
                // 009-ui-fixes-next-iteration, US9, FR-027/028: the derived region-pair label
                // replaces the raw SKU here for AWSDataTransfer Services; every other Service
                // is unaffected (FR-030) since this is `null` for them.
                const dataTransferLabel = awsDataTransferLabel(
                  item.service_code,
                  skuAttributesById.get(item.sku_selection_id) ?? {},
                );
                // 021 US7 (FR-047): a readable name and description, with the codes muted.
                const label = skuLabelsById.get(item.sku_selection_id);
                const readable = label?.readable ? label : null;
                return (
                  <PriceLine
                    key={item.sku_selection_id}
                    text={
                      readable
                        ? serviceLabelText(readable)
                        : `${item.service_code} / ${dataTransferLabel ?? item.sku}`
                    }
                    codes={readable?.codes}
                    price={formatPrice(item.price!)}
                    wordWrap={wordWrap}
                    detail={<LineDetail item={item} />}
                  />
                );
              })}
            </ul>
            <div className="flex items-center justify-between gap-2 border-t border-border pt-1 text-2xs font-medium">
              <span>{group.region} total</span>
              <span className="tabular-nums">{formatPrice(String(group.subtotal))}</span>
            </div>
          </div>
        ))}
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
  detail,
  codes,
}: {
  text: string;
  price: string;
  wordWrap: boolean;
  detail?: React.ReactNode;
  /** 021 US7: "service_code / sku", muted under a readable label. */
  codes?: string;
}) {
  const [labelRef, labelWidth] = useMeasuredWidth<HTMLSpanElement>();

  const { firstLine, remainder } =
    wordWrap && labelWidth !== null
      ? splitForWrap(text, labelWidth, (s) => measureTextWidth(s, priceLineFont()))
      : { firstLine: text, remainder: null };

  return (
    <li className="flex flex-col gap-0.5 text-2xs">
      <div className="flex items-center justify-between gap-2">
        <span
          ref={labelRef}
          title={text}
          className={wordWrap ? "min-w-0 flex-1" : "min-w-0 flex-1 truncate"}
        >
          {wordWrap ? firstLine : text}
        </span>
        <span className="shrink-0 tabular-nums">{price}</span>
      </div>
      {wordWrap && remainder !== null && <p className="pl-[2ch]">{remainder}</p>}
      {codes && <p className="truncate pl-[2ch] text-muted-foreground">{codes}</p>}
      {detail}
    </li>
  );
}
