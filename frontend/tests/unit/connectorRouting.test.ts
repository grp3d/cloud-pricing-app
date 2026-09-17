import { describe, expect, it } from "vitest";

import {
  chooseConnectorSides,
  routeAroundObstacles,
  sampleCubicBezier,
  sampleQuadraticBezier,
  type ConnectorSide,
  type Point,
  type Rect,
} from "../../src/lib/connectorRouting";

const NO_USAGE: Record<ConnectorSide, number> = { top: 0, right: 0, bottom: 0, left: 0 };

function usage(overrides: Partial<Record<ConnectorSide, number>>): Record<ConnectorSide, number> {
  return { ...NO_USAGE, ...overrides };
}

const BOX = (x: number, y: number): Rect => ({ x, y, width: 100, height: 100 });

describe("chooseConnectorSides", () => {
  it("picks right/left for boxes side by side horizontally, with open sides", () => {
    const from = BOX(0, 0);
    const to = BOX(300, 0);
    expect(chooseConnectorSides(from, to, NO_USAGE, NO_USAGE)).toEqual({
      fromSide: "right",
      toSide: "left",
    });
  });

  it("picks bottom/top for boxes stacked vertically", () => {
    const from = BOX(0, 0);
    const to = BOX(0, 300);
    expect(chooseConnectorSides(from, to, NO_USAGE, NO_USAGE)).toEqual({
      fromSide: "bottom",
      toSide: "top",
    });
  });

  it("mirrors left/right when the target is to the left instead", () => {
    const from = BOX(300, 0);
    const to = BOX(0, 0);
    expect(chooseConnectorSides(from, to, NO_USAGE, NO_USAGE)).toEqual({
      fromSide: "left",
      toSide: "right",
    });
  });

  it("falls back to the next-shortest-path side when the ideal side is already occupied", () => {
    const from = BOX(0, 0);
    const to = BOX(300, 0); // ideal fromSide is "right"
    const fromUsage = usage({ right: 2 }); // right already taken; top/bottom/left are open
    const { fromSide } = chooseConnectorSides(from, to, fromUsage, NO_USAGE);
    expect(fromSide).not.toBe("right");
    expect(["top", "bottom"]).toContain(fromSide); // top/bottom are equidistant and shorter than left
  });

  it("never picks an occupied side while any side is still open", () => {
    const from = BOX(0, 0);
    const to = BOX(300, 0);
    const fromUsage = usage({ right: 1, top: 1, bottom: 1 }); // only "left" is open
    const { fromSide } = chooseConnectorSides(from, to, fromUsage, NO_USAGE);
    expect(fromSide).toBe("left");
  });

  it("when every side is occupied, picks the side with the fewest connectors", () => {
    const from = BOX(0, 0);
    const to = BOX(300, 0);
    const fromUsage = usage({ right: 3, top: 2, bottom: 2, left: 1 });
    const { fromSide } = chooseConnectorSides(from, to, fromUsage, NO_USAGE);
    expect(fromSide).toBe("left");
  });

  it("ties in occupied-side counts still break by shortest path", () => {
    const from = BOX(0, 0);
    const to = BOX(300, 0); // ideal is "right"
    // Every side has exactly 1 connector -- "right" (shortest path) should win the tie.
    const fromUsage = usage({ right: 1, top: 1, bottom: 1, left: 1 });
    const { fromSide } = chooseConnectorSides(from, to, fromUsage, NO_USAGE);
    expect(fromSide).toBe("right");
  });

  it("chooses each box's side independently -- one box's usage doesn't affect the other's", () => {
    const from = BOX(0, 0);
    const to = BOX(300, 0);
    const fromUsage = usage({ right: 5 });
    const toUsage = NO_USAGE;
    const { toSide } = chooseConnectorSides(from, to, fromUsage, toUsage);
    expect(toSide).toBe("left"); // unaffected by `from`'s occupied "right" side
  });
});

// A segment/rect intersection check independent of `routeAroundObstacles`'s own implementation
// (Liang-Barsky), so a bug in one isn't masked by an identical bug in the other -- used below
// purely to assert "this detour segment does not cross this obstacle", not to re-derive the
// detour itself.
function segmentCrossesRect(a: Point, b: Point, rect: Rect): boolean {
  const left = rect.x;
  const right = rect.x + rect.width;
  const top = rect.y;
  const bottom = rect.y + rect.height;
  const minX = Math.min(a.x, b.x);
  const maxX = Math.max(a.x, b.x);
  const minY = Math.min(a.y, b.y);
  const maxY = Math.max(a.y, b.y);
  // Both test segments below are axis-aligned (routeAroundObstacles only ever returns
  // horizontal or vertical segments), so a plain bounding-box overlap check is exact, not an
  // approximation.
  return minX < right && maxX > left && minY < bottom && maxY > top;
}

function pathClearsObstacle(path: Point[], obstacle: Rect): boolean {
  for (let i = 0; i < path.length - 1; i++) {
    if (segmentCrossesRect(path[i], path[i + 1], obstacle)) return false;
  }
  return true;
}

describe("routeAroundObstacles", () => {
  it("returns null when the straight line is already clear", () => {
    const source = { x: 0, y: 50 };
    const target = { x: 300, y: 50 };
    const obstacle = BOX(0, 300); // well below the line, not in the way
    expect(routeAroundObstacles(source, target, [obstacle])).toBeNull();
  });

  it("returns null with no obstacles at all", () => {
    const source = { x: 0, y: 0 };
    const target = { x: 300, y: 0 };
    expect(routeAroundObstacles(source, target, [])).toBeNull();
  });

  it("detours around a box sitting directly between two horizontally-aligned boxes", () => {
    const source = { x: 0, y: 50 };
    const target = { x: 300, y: 50 };
    const obstacle = { x: 100, y: 0, width: 100, height: 100 }; // straddles the line
    const route = routeAroundObstacles(source, target, [obstacle]);
    expect(route).not.toBeNull();
    expect(route![0]).toEqual(source);
    expect(route![route!.length - 1]).toEqual(target);
    expect(pathClearsObstacle(route!, obstacle)).toBe(true);
  });

  it("detours around a box sitting directly between two vertically-aligned boxes", () => {
    const source = { x: 50, y: 0 };
    const target = { x: 50, y: 300 };
    const obstacle = { x: 0, y: 100, width: 100, height: 100 }; // straddles the line
    const route = routeAroundObstacles(source, target, [obstacle]);
    expect(route).not.toBeNull();
    expect(pathClearsObstacle(route!, obstacle)).toBe(true);
    // Vertical line (dy > dx) -> detour is horizontal (constant x on the middle two points).
    expect(route![1].x).toBe(route![2].x);
  });

  it("picks the shorter detour side when the line's midpoint is closer to one side", () => {
    const source = { x: 0, y: 10 }; // near the obstacle's top
    const target = { x: 300, y: 10 };
    const obstacle = { x: 100, y: 0, width: 100, height: 200 }; // midpoint (10) is near top (0)
    const route = routeAroundObstacles(source, target, [obstacle]);
    // Detouring over the top (y < obstacle.y) is the shorter option here.
    expect(route![1].y).toBeLessThan(obstacle.y);
  });

  it("detours the other way when the midpoint is closer to the opposite side", () => {
    const source = { x: 0, y: 190 }; // near the obstacle's bottom
    const target = { x: 300, y: 190 };
    const obstacle = { x: 100, y: 0, width: 100, height: 200 };
    const route = routeAroundObstacles(source, target, [obstacle]);
    expect(route![1].y).toBeGreaterThan(obstacle.y + obstacle.height);
  });

  it("uses the combined bounding box of multiple blocking obstacles", () => {
    const source = { x: 0, y: 50 };
    const target = { x: 400, y: 50 };
    const first = { x: 100, y: 0, width: 50, height: 100 };
    const second = { x: 250, y: 0, width: 50, height: 100 };
    const route = routeAroundObstacles(source, target, [first, second]);
    expect(route).not.toBeNull();
    expect(pathClearsObstacle(route!, first)).toBe(true);
    expect(pathClearsObstacle(route!, second)).toBe(true);
  });

  it("ignores an obstacle that isn't actually on the line", () => {
    const source = { x: 0, y: 50 };
    const target = { x: 300, y: 50 };
    const nearby = { x: 100, y: 500, width: 100, height: 100 }; // far below the line
    expect(routeAroundObstacles(source, target, [nearby])).toBeNull();
  });

  it("extraOffset pushes the detour further from the obstacle, in the outward direction", () => {
    const source = { x: 0, y: 190 }; // detours below (per the earlier test)
    const target = { x: 300, y: 190 };
    const obstacle = { x: 100, y: 0, width: 100, height: 200 };
    const withoutExtra = routeAroundObstacles(source, target, [obstacle]);
    const withExtra = routeAroundObstacles(source, target, [obstacle], 30);
    expect(withExtra![1].y).toBe(withoutExtra![1].y + 30);
  });

  // Live user report #2: an obstacle sitting under a *bulging* default bezier curve, whose
  // straight source->target line itself does not cross it -- routeAroundObstacles missed this
  // entirely until it could be told what the actual rendered curve looks like via `pathSamples`.
  describe("pathSamples", () => {
    it("returns null (straight-line-only behavior) when pathSamples is omitted, even if a curve would have crossed the obstacle", () => {
      const source = { x: 0, y: 50 };
      const target = { x: 300, y: 50 };
      // Well clear of the straight line, but this obstacle sits where a bulging curve might go.
      const obstacle = { x: 100, y: 100, width: 100, height: 100 };
      expect(routeAroundObstacles(source, target, [obstacle])).toBeNull();
    });

    it("detects an obstacle the straight line misses but a sampled curve crosses", () => {
      const source = { x: 0, y: 50 };
      const target = { x: 300, y: 50 };
      const obstacle = { x: 100, y: 100, width: 100, height: 100 }; // below the straight line
      // A curve that bulges downward through the obstacle, even though source/target themselves
      // (the curve's own first/last sample) sit above it on the clear straight line.
      const pathSamples = [source, { x: 150, y: 150 }, target];
      const route = routeAroundObstacles(source, target, [obstacle], 0, pathSamples);
      expect(route).not.toBeNull();
      expect(pathClearsObstacle(route!, obstacle)).toBe(true);
    });

    it("ignores pathSamples with fewer than 2 points and falls back to the straight line", () => {
      const source = { x: 0, y: 50 };
      const target = { x: 300, y: 50 };
      const obstacle = { x: 100, y: 0, width: 100, height: 100 }; // straddles the straight line
      const route = routeAroundObstacles(source, target, [obstacle], 0, [source]);
      expect(route).not.toBeNull(); // still caught via the straight-line fallback
    });
  });
});

describe("sampleCubicBezier", () => {
  it("starts at p0 and ends at p3", () => {
    const p0 = { x: 0, y: 0 };
    const p1 = { x: 10, y: 50 };
    const p2 = { x: 90, y: 50 };
    const p3 = { x: 100, y: 0 };
    const points = sampleCubicBezier(p0, p1, p2, p3, 10);
    expect(points[0]).toEqual(p0);
    expect(points[points.length - 1]).toEqual(p3);
    expect(points).toHaveLength(11);
  });

  it("collapses to the straight line when both control points sit on it", () => {
    const p0 = { x: 0, y: 0 };
    const p3 = { x: 100, y: 0 };
    const points = sampleCubicBezier(p0, { x: 33, y: 0 }, { x: 66, y: 0 }, p3, 4);
    for (const p of points) expect(p.y).toBeCloseTo(0);
  });
});

describe("sampleQuadraticBezier", () => {
  it("starts at p0 and ends at p2", () => {
    const p0 = { x: 0, y: 0 };
    const control = { x: 50, y: 100 };
    const p2 = { x: 100, y: 0 };
    const points = sampleQuadraticBezier(p0, control, p2, 8);
    expect(points[0]).toEqual(p0);
    expect(points[points.length - 1]).toEqual(p2);
    expect(points).toHaveLength(9);
  });

  it("bulges toward the control point at its midpoint", () => {
    const p0 = { x: 0, y: 0 };
    const control = { x: 50, y: 100 };
    const p2 = { x: 100, y: 0 };
    const points = sampleQuadraticBezier(p0, control, p2, 2);
    // At t=0.5, a quadratic bezier sits at the midpoint of the two edge-midpoints -- halfway
    // between the line's own midpoint (50,0) and the control point (50,100).
    expect(points[1]).toEqual({ x: 50, y: 50 });
  });
});
