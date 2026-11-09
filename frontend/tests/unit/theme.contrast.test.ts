import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * 021 (FR-026, FR-031, research R8, data-model §3): the theme's colour tokens meet WCAG 2.1 AA
 * in light and dark. The values are read straight from `src/index.css`, so this checks what
 * ships. OKLCH → linear sRGB uses the published OKLab matrices; no dependency needed.
 */

const css = readFileSync(resolve(__dirname, "../../src/index.css"), "utf8");

type Oklch = { l: number; c: number; h: number };

function block(selector: ":root" | ".dark"): Record<string, Oklch> {
  const start = css.search(new RegExp(`^${selector.replace(".", "\\.")} \\{`, "m"));
  if (start < 0) throw new Error(`${selector} block not found`);
  const body = css.slice(start, css.indexOf("\n}", start));
  const tokens: Record<string, Oklch> = {};
  const re = /--([a-z0-9-]+):\s*oklch\(\s*([\d.]+)(%?)\s+([\d.]+)\s+([\d.]+)\s*\)/g;
  for (const m of body.matchAll(re)) {
    tokens[m[1]] = {
      l: m[3] === "%" ? Number(m[2]) / 100 : Number(m[2]),
      c: Number(m[4]),
      h: Number(m[5]),
    };
  }
  return tokens;
}

function luminance({ l, c, h }: Oklch): number {
  const a = c * Math.cos((h * Math.PI) / 180);
  const b = c * Math.sin((h * Math.PI) / 180);
  const l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s_ = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  const r = clamp(4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_);
  const g = clamp(-1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_);
  const bl = clamp(-0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_);
  // Linear sRGB is what WCAG's relative luminance is defined on.
  return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
}

function contrast(a: Oklch, b: Oklch): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const TEXT_PAIRS: [string, string][] = [
  ["foreground", "background"],
  ["foreground", "card"],
  ["foreground", "muted"],
  ["card-foreground", "card"],
  ["popover-foreground", "popover"],
  ["muted-foreground", "background"],
  ["muted-foreground", "card"],
  ["muted-foreground", "muted"],
  ["muted-foreground", "sidebar"],
  ["primary-foreground", "primary"],
  ["secondary-foreground", "secondary"],
  ["accent-foreground", "accent"],
  ["sidebar-foreground", "sidebar"],
  ["sidebar-primary-foreground", "sidebar-primary"],
  // 021 US5 (FR-035, FR-040): the dark header and the soft (light-blue) button.
  ["header-foreground", "header"],
  ["header-foreground", "header-accent"],
  ["header-muted-foreground", "header"],
  ["header-muted-foreground", "header-accent"],
  ["primary-soft-foreground", "primary-soft"],
  ["primary-soft-foreground", "background"],
];
const NON_TEXT_PAIRS: [string, string][] = [
  ["ring", "background"],
  ["ring", "card"],
  ["input", "background"],
  ["input", "card"],
  ["ring", "sidebar"],
  ["header-ring", "header"],
  ["header-ring", "header-accent"],
];

describe.each([":root", ".dark"] as const)("theme tokens in %s", (selector) => {
  const t = block(selector);

  it.each(TEXT_PAIRS)("%s on %s is at least 4.5:1", (fg, bg) => {
    expect(t[fg], fg).toBeDefined();
    expect(t[bg], bg).toBeDefined();
    expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(4.5);
  });

  it.each(NON_TEXT_PAIRS)("%s on %s is at least 3:1", (fg, bg) => {
    expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(3);
  });

  it("uses one blue accent on zinc neutrals", () => {
    expect(t.primary.h).toBeGreaterThanOrEqual(250);
    expect(t.primary.h).toBeLessThanOrEqual(270);
    expect(t.ring.h).toBeGreaterThanOrEqual(250);
    expect(t.ring.h).toBeLessThanOrEqual(270);
    for (const name of [
      "background",
      "foreground",
      "card",
      "muted",
      "border",
      "sidebar",
      "header",
      "header-accent",
    ]) {
      expect(t[name].c, name).toBeLessThan(0.01);
    }
  });
});
