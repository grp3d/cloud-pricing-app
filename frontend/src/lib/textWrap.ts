/**
 * Pure line-splitting logic for the Pricing column's word-wrap toggle
 * (009-ui-fixes-next-iteration follow-up). Off (the default), a Price per Sku line behaves
 * exactly as it always has — a single line, truncated with the browser's own CSS ellipsis
 * when too long, the rest of the text silently gone. On, that first line stays visually
 * identical (a real ellipsis where the natural cutoff falls), but whatever didn't fit is no
 * longer discarded — this computes the same cutoff point and returns the leftover text for
 * the caller to render as a second, indented line, rather than losing it.
 *
 * `measureText` is injected rather than this module reaching for a real `<canvas>` itself, so
 * it's testable with a deterministic fake measurer (matching `dropTargetDetection.ts`'s/
 * `nodeLayout.ts`'s no-DOM-dependency precedent) — the real caller supplies a canvas-based
 * measurer using the label's own actual computed font, so the cutoff matches what the
 * browser would have truncated to, pixel for pixel.
 */

const ELLIPSIS = "…";

export interface WrapResult {
  /** The text to show on the first line — already carrying a trailing `ELLIPSIS` whenever
   * `remainder` is non-null. Equal to the original `text` verbatim when it already fits (no
   * ellipsis added, matching today's un-truncated single-line case). */
  firstLine: string;
  /** Whatever didn't fit on the first line, or `null` when the whole `text` already fits
   * within `maxWidthPx` and no split was needed. May itself still be long — the caller lets
   * it wrap normally (not this module's concern; it only ever produces one cut). */
  remainder: string | null;
}

/** Splits `text` so `firstLine` (plus a trailing ellipsis) fits within `maxWidthPx`, per
 * `measureText`. Never splits to an empty first line — even a single character wider than
 * the whole budget still gets shown, rather than vanishing. `maxWidthPx <= 0` is treated as
 * "not measured yet" (e.g. before the label's own ref has laid out) and returns `text`
 * unsplit, deferring to the next real measurement rather than truncating against a
 * degenerate width. */
export function splitForWrap(
  text: string,
  maxWidthPx: number,
  measureText: (s: string) => number,
): WrapResult {
  if (maxWidthPx <= 0 || measureText(text) <= maxWidthPx) {
    return { firstLine: text, remainder: null };
  }

  const budget = maxWidthPx - measureText(ELLIPSIS);
  if (budget <= 0) {
    return { firstLine: ELLIPSIS, remainder: text };
  }

  // Longest prefix whose rendered width fits within `budget` — binary search over length,
  // valid since every additional character can only add non-negative width.
  let lo = 0;
  let hi = text.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (measureText(text.slice(0, mid)) <= budget) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }
  const cut = Math.max(lo, 1);

  return { firstLine: text.slice(0, cut) + ELLIPSIS, remainder: text.slice(cut) };
}
