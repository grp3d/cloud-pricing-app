import { describe, expect, it } from "vitest";

import { splitForWrap } from "../../src/lib/textWrap";

/** Deterministic fake measurer: every character is exactly 6px wide, so exact split points
 * are easy to predict by hand (no real font/canvas involved). */
const fixedWidth = (s: string) => s.length * 6;

describe("splitForWrap", () => {
  it("returns the text unsplit when it already fits", () => {
    const result = splitForWrap("AmazonEC2 / SKU", 200, fixedWidth);
    expect(result).toEqual({ firstLine: "AmazonEC2 / SKU", remainder: null });
  });

  it("splits when the text is too wide, keeping the concatenation lossless", () => {
    const text = "AmazonEC2 / 22XDKSBPSX27AZ8U";
    const result = splitForWrap(text, 60, fixedWidth);
    expect(result.remainder).not.toBeNull();
    expect(result.firstLine.endsWith("…")).toBe(true);
    // Stripping the trailing ellipsis and rejoining with the remainder reconstructs the
    // original text exactly — nothing is silently dropped.
    expect(result.firstLine.slice(0, -1) + result.remainder!).toBe(text);
  });

  it("computes the exact cutoff for a known fixed-width measurer", () => {
    // budget = maxWidthPx(20) - ellipsisWidth(6) = 14 -> floor(14/6) = 2 characters fit.
    const result = splitForWrap("ABCDEFGH", 20, fixedWidth);
    expect(result).toEqual({ firstLine: "AB…", remainder: "CDEFGH" });
  });

  it("treats a non-positive maxWidthPx as 'not measured yet' and returns the text unsplit", () => {
    expect(splitForWrap("AmazonEC2 / SKU", 0, fixedWidth)).toEqual({
      firstLine: "AmazonEC2 / SKU",
      remainder: null,
    });
    expect(splitForWrap("AmazonEC2 / SKU", -10, fixedWidth)).toEqual({
      firstLine: "AmazonEC2 / SKU",
      remainder: null,
    });
  });

  it("still shows one character even when the ellipsis alone doesn't fit the budget", () => {
    // ellipsisWidth(6) >= maxWidthPx(5) -> budget <= 0, but a first line still isn't empty.
    const result = splitForWrap("AmazonEC2", 5, fixedWidth);
    expect(result.firstLine).toBe("…");
    expect(result.remainder).toBe("AmazonEC2");
  });

  it("never returns an empty first line even for a single very-wide character", () => {
    const wideFirstChar = (s: string) => (s.startsWith("W") ? 1000 : s.length * 6);
    const result = splitForWrap("Wide rest of text", 50, wideFirstChar);
    expect(result.firstLine.length).toBeGreaterThan(0);
    expect(result.firstLine.endsWith("…")).toBe(true);
  });

  it("round-trips correctly with a non-uniform (per-character) measurer", () => {
    const widths: Record<string, number> = { i: 2, m: 10, " ": 3 };
    const measure = (s: string) =>
      [...s].reduce((sum, ch) => sum + (widths[ch] ?? 6), 0);
    const text = "mmmmmiiiii mmmmm";
    const result = splitForWrap(text, 40, measure);
    expect(result.remainder).not.toBeNull();
    expect(result.firstLine.slice(0, -1) + result.remainder!).toBe(text);
    // The first line (minus its ellipsis) must actually fit within the budget.
    const ellipsisWidth = measure("…");
    expect(measure(result.firstLine.slice(0, -1))).toBeLessThanOrEqual(40 - ellipsisWidth);
  });
});
