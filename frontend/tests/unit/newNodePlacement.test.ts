import { describe, expect, it } from "vitest";

import { findVisibleSlot, flowGridSlots, type Rect } from "../../src/lib/newNodePlacement";

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

// 016-canvas-icon-layout (validation fix, research.md §11a): default slots for top-level boxes
// flow by each box's real size so wider/taller icon boxes never overlap.
describe("flowGridSlots", () => {
  it("places boxes left to right by their widths with an 80px gap", () => {
    const slots = flowGridSlots([
      { width: 320, height: 200 },
      { width: 220, height: 100 },
    ]);
    expect(slots).toEqual([
      { x: 0, y: 0 },
      { x: 400, y: 0 },
    ]);
  });

  it("starts a new row after 4 boxes, below the tallest box of the row plus 40px", () => {
    const sizes = [
      { width: 100, height: 50 },
      { width: 100, height: 300 },
      { width: 100, height: 50 },
      { width: 100, height: 50 },
      { width: 100, height: 50 },
    ];
    const slots = flowGridSlots(sizes);
    expect(slots[3]).toEqual({ x: 540, y: 0 });
    expect(slots[4]).toEqual({ x: 0, y: 340 });
  });

  it("never lets default slots in a row overlap", () => {
    const sizes = [320, 380, 220, 200].map((width) => ({ width, height: 100 }));
    const slots = flowGridSlots(sizes);
    for (let i = 1; i < slots.length; i++) {
      expect(slots[i].x).toBeGreaterThanOrEqual(slots[i - 1].x + sizes[i - 1].width);
    }
  });
});
