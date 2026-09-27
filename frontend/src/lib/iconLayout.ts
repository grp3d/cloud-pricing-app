/**
 * Geometry for service icons inside a canvas box (016-canvas-icon-layout, FR-001–FR-008,
 * research.md §7, data-model.md §5–6). Pure — no DOM, no React Flow — so every placement rule
 * is unit-testable, matching `nodeLayout.ts`/`dropTargetDetection.ts`.
 *
 * Coordinates are canvas units relative to the top-left of a box's icon area (inside the box's
 * padding, below its name). Icons are 60px squares (2.5× 015's 24px) kept at least one icon
 * width (60px) apart — both the default spacing and the closest a drag may place them (reduced
 * from an initial 90px, which spread boxes out too much): two icons are far enough apart when
 * they're a full `STEP` apart on at least one axis, so the gap between them is ≥ `GAP`.
 */

export const ICON = 60;
export const GAP = 60;
export const MAX_PER_ROW = 3;
/** The box's own padding (`p-2`). */
export const PAD = 8;
/** Room below the last icon row for the box's bottom-right region label (010, FR-019). */
export const LABEL_RESERVE = 16;
/** Box border allowance (a 2px border on each side). */
export const BORDER = 4;
/** Distance between the top-left corners of two adjacent icons. */
export const STEP = ICON + GAP;
/** The narrowest a box may be resized to: one icon plus padding and borders. */
export const MIN_ICON_BOX_WIDTH = 2 * PAD + ICON + BORDER;

export interface IconPosition {
  x: number;
  y: number;
}

export type IconPositions = Record<string, IconPosition>;

/** Default width for a box holding `count` icons: wide enough for its widest row (at most
 * `MAX_PER_ROW`), never narrower than `minWidth` (today's per-box-type default). */
export function defaultBoxWidth(count: number, minWidth: number): number {
  const perRow = Math.min(count, MAX_PER_ROW);
  if (perRow <= 1) return minWidth;
  return Math.max(minWidth, 2 * PAD + perRow * ICON + (perRow - 1) * GAP + BORDER);
}

/** The icon area's width inside a box of `boxWidth`. */
export function innerWidthOf(boxWidth: number): number {
  return Math.max(ICON, boxWidth - 2 * PAD - BORDER);
}

function perRowFor(innerWidth: number): number {
  return Math.max(1, Math.min(MAX_PER_ROW, Math.floor((innerWidth + GAP) / STEP)));
}

function slot(index: number, perRow: number): IconPosition {
  return { x: (index % perRow) * STEP, y: Math.floor(index / perRow) * STEP };
}

/** Default placement: row-major in service order, up to 3 per row (fewer if the area is
 * narrower), one `STEP` apart. */
export function defaultPositions(ids: string[], innerWidth: number): IconPositions {
  const perRow = perRowFor(innerWidth);
  return Object.fromEntries(ids.map((id, i) => [id, slot(i, perRow)]));
}

/** Whether `p` keeps the minimum spacing from every icon in `others`. */
export function isValidSpot(p: IconPosition, others: IconPosition[]): boolean {
  return others.every((o) => Math.abs(p.x - o.x) >= STEP || Math.abs(p.y - o.y) >= STEP);
}

/** Keeps a position inside an area of `width` (and `height`, when given). */
export function clampToArea(
  p: IconPosition,
  area: { width: number; height?: number },
): IconPosition {
  const maxX = Math.max(0, area.width - ICON);
  const maxY = area.height === undefined ? Infinity : Math.max(0, area.height - ICON);
  return {
    x: Math.min(Math.max(0, p.x), maxX),
    y: Math.min(Math.max(0, p.y), maxY),
  };
}

/** The valid spot closest to `p` within `bounds.width` (height is unbounded — the box grows
 * downward). Deterministic: ties prefer the smaller y, then the smaller x. */
export function nearestValidSpot(
  p: IconPosition,
  others: IconPosition[],
  bounds: { width: number },
): IconPosition {
  const start = clampToArea(p, bounds);
  if (isValidSpot(start, others)) return start;

  const maxX = Math.max(0, bounds.width - ICON);
  const lowest = others.reduce((max, o) => Math.max(max, o.y), start.y);
  const fine = ICON / 4;

  const xs = new Set<number>([start.x, 0, maxX]);
  for (let x = 0; x <= maxX; x += fine) xs.add(x);
  const ys = new Set<number>([start.y, 0, lowest + STEP]);
  for (let y = 0; y <= lowest + STEP; y += fine) ys.add(y);
  for (const o of others) {
    for (const x of [o.x - STEP, o.x + STEP]) if (x >= 0 && x <= maxX) xs.add(x);
    for (const y of [o.y - STEP, o.y + STEP]) if (y >= 0) ys.add(y);
  }

  let best: IconPosition | null = null;
  let bestDistance = Infinity;
  for (const y of [...ys].sort((a, b) => a - b)) {
    for (const x of [...xs].sort((a, b) => a - b)) {
      const candidate = { x, y };
      if (!isValidSpot(candidate, others)) continue;
      const distance = Math.hypot(x - start.x, y - start.y);
      if (distance < bestDistance) {
        best = candidate;
        bestDistance = distance;
      }
    }
  }
  return best ?? { x: start.x, y: lowest + STEP };
}

/** Height the icon area needs: down to the lowest icon plus the region-label reserve. */
export function contentHeight(positions: IconPositions): number {
  const ys = Object.values(positions).map((p) => p.y);
  if (ys.length === 0) return 0;
  return Math.max(...ys) + ICON + LABEL_RESERVE;
}

/** Final positions for `ids`: saved (hand-placed) positions that still fit and keep their
 * spacing are kept as-is; every other icon takes the first free default slot, without moving
 * the kept ones (FR-008, spec Edge Cases). */
export function resolvePositions(
  ids: string[],
  saved: IconPositions,
  innerWidth: number,
): IconPositions {
  const result: IconPositions = {};
  const placed: IconPosition[] = [];

  for (const id of ids) {
    const p = saved[id];
    if (!p) continue;
    const inside = p.x >= 0 && p.y >= 0 && p.x + ICON <= innerWidth;
    if (inside && isValidSpot(p, placed)) {
      result[id] = p;
      placed.push(p);
    }
  }

  const perRow = perRowFor(innerWidth);
  let index = 0;
  for (const id of ids) {
    if (result[id]) continue;
    let candidate = slot(index, perRow);
    while (!isValidSpot(candidate, placed)) candidate = slot(++index, perRow);
    result[id] = candidate;
    placed.push(candidate);
    index++;
  }
  return result;
}
