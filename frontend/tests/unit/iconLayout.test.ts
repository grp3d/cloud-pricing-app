import { describe, expect, it } from "vitest";

import {
  GAP,
  ICON,
  LABEL_RESERVE,
  MAX_PER_ROW,
  PAD,
  clampToArea,
  contentHeight,
  defaultBoxWidth,
  defaultPositions,
  innerWidthOf,
  isValidSpot,
  nearestValidSpot,
  resolvePositions,
} from "../../src/lib/iconLayout";

const STEP = ICON + GAP; // 120

describe("constants", () => {
  it("match the spec (60px icons, one-icon gap, 3 per row)", () => {
    expect(ICON).toBe(60);
    expect(GAP).toBe(60);
    expect(MAX_PER_ROW).toBe(3);
    expect(PAD).toBe(8);
    expect(LABEL_RESERVE).toBe(16);
  });
});

describe("defaultBoxWidth", () => {
  it("keeps today's minimum for 0 or 1 icon", () => {
    expect(defaultBoxWidth(0, 220)).toBe(220);
    expect(defaultBoxWidth(1, 200)).toBe(200);
  });

  it("widens for 2 icons", () => {
    expect(defaultBoxWidth(2, 200)).toBe(2 * PAD + 2 * ICON + GAP + 4);
  });

  it("fits at most 3 per row (320 with borders)", () => {
    expect(defaultBoxWidth(3, 220)).toBe(320);
    expect(defaultBoxWidth(10, 220)).toBe(320);
  });
});

describe("innerWidthOf", () => {
  it("removes padding and borders", () => {
    expect(innerWidthOf(380)).toBe(360);
  });
});

describe("defaultPositions", () => {
  it("lays icons out row-major, 3 per row, 120 apart", () => {
    const positions = defaultPositions(["a", "b", "c", "d"], 360);
    expect(positions).toEqual({
      a: { x: 0, y: 0 },
      b: { x: STEP, y: 0 },
      c: { x: 2 * STEP, y: 0 },
      d: { x: 0, y: STEP },
    });
  });

  it("wraps earlier when the area is narrower", () => {
    expect(defaultPositions(["a", "b"], 60)).toEqual({
      a: { x: 0, y: 0 },
      b: { x: 0, y: STEP },
    });
  });
});

describe("isValidSpot", () => {
  it("accepts spots separated by a full step on either axis", () => {
    expect(isValidSpot({ x: STEP, y: 10 }, [{ x: 0, y: 0 }])).toBe(true);
    expect(isValidSpot({ x: 20, y: STEP }, [{ x: 0, y: 0 }])).toBe(true);
  });

  it("rejects anything closer", () => {
    expect(isValidSpot({ x: STEP - 1, y: 0 }, [{ x: 0, y: 0 }])).toBe(false);
    expect(isValidSpot({ x: 100, y: 100 }, [{ x: 0, y: 0 }])).toBe(false);
  });
});

describe("nearestValidSpot", () => {
  it("returns the drop point when it's already valid", () => {
    expect(nearestValidSpot({ x: 200, y: 0 }, [{ x: 0, y: 0 }], { width: 360 })).toEqual({
      x: 200,
      y: 0,
    });
  });

  it("moves an overlapping drop to the closest valid spot", () => {
    const spot = nearestValidSpot({ x: 10, y: 0 }, [{ x: 0, y: 0 }], { width: 360 });
    expect(isValidSpot(spot, [{ x: 0, y: 0 }])).toBe(true);
    expect(spot).toEqual({ x: STEP, y: 0 });
  });

  it("never leaves the box's width, extending downward instead", () => {
    const others = [{ x: 0, y: 0 }];
    const spot = nearestValidSpot({ x: 500, y: 0 }, others, { width: 60 });
    expect(spot.x).toBe(0);
    expect(spot.y).toBe(STEP);
  });

  it("clamps negative coordinates into the box", () => {
    expect(nearestValidSpot({ x: -40, y: -40 }, [], { width: 360 })).toEqual({ x: 0, y: 0 });
  });
});

describe("contentHeight", () => {
  it("is 0 with no icons", () => {
    expect(contentHeight({})).toBe(0);
  });

  it("covers the lowest icon plus the label reserve", () => {
    expect(contentHeight({ a: { x: 0, y: 0 }, b: { x: 0, y: STEP } })).toBe(
      STEP + ICON + LABEL_RESERVE,
    );
  });
});

describe("resolvePositions", () => {
  it("keeps valid saved positions and places new icons in the first free slot", () => {
    const resolved = resolvePositions(["a", "b"], { a: { x: 0, y: 0 } }, 360);
    expect(resolved.a).toEqual({ x: 0, y: 0 });
    expect(resolved.b).toEqual({ x: STEP, y: 0 });
  });

  it("doesn't move hand-placed icons when a new one arrives", () => {
    const saved = { a: { x: STEP, y: 0 } };
    const resolved = resolvePositions(["a", "b"], saved, 360);
    expect(resolved.a).toEqual({ x: STEP, y: 0 });
    expect(resolved.b).toEqual({ x: 0, y: 0 });
  });

  it("replaces a saved position that overlaps another icon", () => {
    const saved = { a: { x: 0, y: 0 }, b: { x: 10, y: 10 } };
    const resolved = resolvePositions(["a", "b"], saved, 360);
    expect(resolved.a).toEqual({ x: 0, y: 0 });
    expect(isValidSpot(resolved.b, [resolved.a])).toBe(true);
  });

  it("replaces a saved position outside the box", () => {
    const resolved = resolvePositions(["a"], { a: { x: 900, y: 0 } }, 360);
    expect(resolved.a).toEqual({ x: 0, y: 0 });
  });
});

describe("clampToArea", () => {
  it("keeps an icon inside the area", () => {
    expect(clampToArea({ x: 999, y: -5 }, { width: 360 })).toEqual({ x: 300, y: 0 });
    expect(clampToArea({ x: 10, y: 999 }, { width: 360, height: 210 })).toEqual({ x: 10, y: 150 });
  });
});
