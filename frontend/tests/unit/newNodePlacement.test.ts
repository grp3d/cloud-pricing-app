import { describe, expect, it } from "vitest";

import { findVisibleSlot, type Rect } from "../../src/lib/newNodePlacement";

const visible: Rect = { x: 1000, y: 500, width: 800, height: 600 };
const size = { width: 220, height: 100 };

describe("findVisibleSlot (016, FR-013)", () => {
  it("uses the visible top-left (plus margin) on an empty canvas", () => {
    expect(findVisibleSlot(visible, [], size)).toEqual({ x: 1024, y: 524, ...size });
  });

  it("returns the first fully-visible spot that overlaps no existing box", () => {
    const occupied: Rect[] = [{ x: 1024, y: 524, width: 220, height: 100 }];
    const slot = findVisibleSlot(visible, occupied, size);
    expect(slot.y).toBe(524);
    expect(slot.x).toBeGreaterThanOrEqual(1024 + 220 + 24);
    expect(slot.x + slot.width).toBeLessThanOrEqual(visible.x + visible.width);
  });

  it("wraps to the next row when a row is full", () => {
    const occupied: Rect[] = [{ x: 1000, y: 500, width: 800, height: 150 }];
    const slot = findVisibleSlot(visible, occupied, size);
    expect(slot.y).toBeGreaterThanOrEqual(650 + 24);
    expect(slot.y + slot.height).toBeLessThanOrEqual(visible.y + visible.height);
  });

  it("falls back to the visible top-left when nothing is free", () => {
    const occupied: Rect[] = [visible];
    expect(findVisibleSlot(visible, occupied, size)).toEqual({ x: 1024, y: 524, ...size });
  });

  it("uses the visible top-left when the box is bigger than the view", () => {
    const big = { width: 2000, height: 2000 };
    expect(findVisibleSlot(visible, [], big)).toEqual({ x: 1000, y: 500, ...big });
  });
});
