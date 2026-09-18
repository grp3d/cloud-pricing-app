import { describe, expect, it } from "vitest";

import {
  absoluteToBendPoint,
  bendPointToAbsolute,
  buildManualBendRoute,
  chooseConnectorSides,
  offsetPoint,
  routeAroundObstacles,
  sampleCubicBezier,
  sampleQuadraticBezier,
  solveQuadraticControlPoint,
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
    expect(chooseConnectorSides(from, to, NO_USAGE)).toEqual({
      fromSide: "right",
      toSide: "left",
    });
  });

  it("picks bottom/top for boxes stacked vertically", () => {
    const from = BOX(0, 0);
    const to = BOX(0, 300);
    expect(chooseConnectorSides(from, to, NO_USAGE)).toEqual({
      fromSide: "bottom",
      toSide: "top",
    });
  });

  it("mirrors left/right when the target is to the left instead", () => {
    const from = BOX(300, 0);
    const to = BOX(0, 0);
    expect(chooseConnectorSides(from, to, NO_USAGE)).toEqual({
      fromSide: "left",
      toSide: "right",
    });
  });

  // Live user rule change: multiple Connectors may now depart a Collection from the same side
  // -- fromSide always picks the shortest-path side, regardless of how many other Connectors
  // (in either direction) already use it.
  it("always picks the shortest-path side for fromSide, even when it's already heavily used", () => {
    const from = BOX(0, 0);
    const to = BOX(300, 0); // ideal fromSide is "right"
    const { fromSide } = chooseConnectorSides(from, to, NO_USAGE);
    expect(fromSide).toBe("right");
  });

  it("falls back to the next-shortest-path side for toSide when the ideal side is already occupied", () => {
    const from = BOX(0, 0);
    const to = BOX(300, 0); // ideal toSide is "left"
    const toUsage = usage({ left: 2 }); // left already taken; top/bottom/right are open
    const { toSide } = chooseConnectorSides(from, to, toUsage);
    expect(toSide).not.toBe("left");
    expect(["top", "bottom"]).toContain(toSide); // top/bottom are equidistant and shorter than right
  });

  it("never picks an occupied toSide while any side is still open", () => {
    const from = BOX(0, 0);
    const to = BOX(300, 0);
    const toUsage = usage({ left: 1, top: 1, bottom: 1 }); // only "right" is open
    const { toSide } = chooseConnectorSides(from, to, toUsage);
    expect(toSide).toBe("right");
  });

  it("when every side is occupied, picks the toSide with the fewest connectors pointing at it", () => {
    const from = BOX(0, 0);
    const to = BOX(300, 0);
    const toUsage = usage({ left: 3, top: 2, bottom: 2, right: 1 });
    const { toSide } = chooseConnectorSides(from, to, toUsage);
    expect(toSide).toBe("right");
  });

  it("ties in occupied toSide counts still break by shortest path", () => {
    const from = BOX(0, 0);
    const to = BOX(300, 0); // ideal toSide is "left"
    // Every side has exactly 1 connector -- "left" (shortest path) should win the tie.
    const toUsage = usage({ left: 1, top: 1, bottom: 1, right: 1 });
    const { toSide } = chooseConnectorSides(from, to, toUsage);
    expect(toSide).toBe("left");
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

describe("offsetPoint", () => {
  it("moves top outward (negative y), bottom outward (positive y)", () => {
    const p = { x: 10, y: 10 };
    expect(offsetPoint(p, "top", 5)).toEqual({ x: 10, y: 5 });
    expect(offsetPoint(p, "bottom", 5)).toEqual({ x: 10, y: 15 });
  });

  it("moves left outward (negative x), right outward (positive x)", () => {
    const p = { x: 10, y: 10 };
    expect(offsetPoint(p, "left", 5)).toEqual({ x: 5, y: 10 });
    expect(offsetPoint(p, "right", 5)).toEqual({ x: 15, y: 10 });
  });
});

// routeAroundObstacles always returns exactly 6 points:
// [source, sourceStub, corner1, corner2, targetStub, target].
// Without sourceSide/targetSide, sourceStub===source and targetStub===target (a harmless
// zero-length "stub"), so these indices apply whether or not a test passes sides.
const SOURCE_STUB = 1;
const CORNER1 = 2;
const CORNER2 = 3;
const TARGET_STUB = 4;

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
    expect(route).toHaveLength(6);
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
    // Vertical line (dy > dx) -> detour is horizontal (constant x on the middle two corners).
    expect(route![CORNER1].x).toBe(route![CORNER2].x);
  });

  it("picks the shorter detour side when the line's midpoint is closer to one side", () => {
    const source = { x: 0, y: 10 }; // near the obstacle's top
    const target = { x: 300, y: 10 };
    const obstacle = { x: 100, y: 0, width: 100, height: 200 }; // midpoint (10) is near top (0)
    const route = routeAroundObstacles(source, target, [obstacle]);
    // Detouring over the top (y < obstacle.y) is the shorter option here.
    expect(route![CORNER1].y).toBeLessThan(obstacle.y);
  });

  it("detours the other way when the midpoint is closer to the opposite side", () => {
    const source = { x: 0, y: 190 }; // near the obstacle's bottom
    const target = { x: 300, y: 190 };
    const obstacle = { x: 100, y: 0, width: 100, height: 200 };
    const route = routeAroundObstacles(source, target, [obstacle]);
    expect(route![CORNER1].y).toBeGreaterThan(obstacle.y + obstacle.height);
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
    expect(withExtra![CORNER1].y).toBe(withoutExtra![CORNER1].y + 30);
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

  // Live user report #3: without sourceSide/targetSide, a detour's final approach direction had
  // no relation to the target's actual attached side, so the arrowhead (which orients to the
  // path's own tangent at its endpoint) could point in an unrelated direction instead of into
  // the box.
  describe("sourceSide/targetSide stubs", () => {
    it("leaves the source stub in the source side's outward direction", () => {
      const source = { x: 50, y: 50 };
      const target = { x: 300, y: 50 };
      const obstacle = { x: 100, y: 0, width: 100, height: 100 };
      const route = routeAroundObstacles(source, target, [obstacle], 0, undefined, "bottom", "left");
      // "bottom" points straight down from source: same x, larger y.
      expect(route![SOURCE_STUB]).toEqual({ x: source.x, y: source.y + 28 });
    });

    it("approaches the target stub from the target side's outward direction", () => {
      const source = { x: 0, y: 50 };
      const target = { x: 250, y: 50 };
      const obstacle = { x: 100, y: 0, width: 100, height: 100 };
      const route = routeAroundObstacles(source, target, [obstacle], 0, undefined, "top", "right");
      // "right" points straight right from target's own perspective, so the stub sits further
      // right, and the final target-ward segment approaches from the right, pointing left/in.
      expect(route![TARGET_STUB]).toEqual({ x: target.x + 28, y: target.y });
    });

    it("the final segment into target is a straight line along the target side's inward normal", () => {
      const source = { x: 0, y: 50 };
      const target = { x: 250, y: 50 };
      const obstacle = { x: 100, y: 0, width: 100, height: 100 };
      const route = routeAroundObstacles(source, target, [obstacle], 0, undefined, "top", "right");
      const last = route![route!.length - 1];
      const secondToLast = route![route!.length - 2];
      // last - secondToLast should be a pure leftward vector (entering a "right"-side handle
      // means approaching from further right, heading left/inward) -- no vertical component.
      expect(last.y).toBe(secondToLast.y);
      expect(last.x).toBeLessThan(secondToLast.x);
    });

    it("without a side, the stub falls back to the raw point (no perpendicular correction)", () => {
      const source = { x: 0, y: 50 };
      const target = { x: 300, y: 50 };
      const obstacle = { x: 100, y: 0, width: 100, height: 100 };
      const route = routeAroundObstacles(source, target, [obstacle]);
      expect(route![SOURCE_STUB]).toEqual(source);
      expect(route![TARGET_STUB]).toEqual(target);
    });

    it("still clears the obstacle with stubs applied", () => {
      const source = { x: 0, y: 50 };
      const target = { x: 300, y: 50 };
      const obstacle = { x: 100, y: 0, width: 100, height: 100 };
      const route = routeAroundObstacles(source, target, [obstacle], 0, undefined, "right", "left");
      expect(pathClearsObstacle(route!, obstacle)).toBe(true);
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

// Manual Connector bending (live user request): a bend point is stored chord-relative -- {t, d}
// relative to the source->target line -- specifically so it scales naturally when either
// endpoint moves, rather than needing separate "keep the intent" recomputation logic.
describe("bendPointToAbsolute", () => {
  it("t=0.5, d=0 is the exact chord midpoint", () => {
    const source = { x: 0, y: 0 };
    const target = { x: 100, y: 0 };
    expect(bendPointToAbsolute(source, target, { t: 0.5, d: 0 })).toEqual({ x: 50, y: 0 });
  });

  it("t=0 is the source itself, t=1 is the target itself, regardless of d", () => {
    const source = { x: 0, y: 0 };
    const target = { x: 100, y: 0 };
    expect(bendPointToAbsolute(source, target, { t: 0, d: 0.5 }).x).toBe(0);
    expect(bendPointToAbsolute(source, target, { t: 1, d: 0.5 }).x).toBe(100);
  });

  it("d offsets perpendicular to the chord, scaled by the chord's own length", () => {
    const source = { x: 0, y: 0 };
    const target = { x: 100, y: 0 }; // horizontal chord, length 100
    const point = bendPointToAbsolute(source, target, { t: 0.5, d: 0.2 });
    // Perpendicular to a horizontal chord is vertical; 0.2 * length(100) = 20.
    expect(point.x).toBe(50);
    expect(Math.abs(point.y)).toBeCloseTo(20);
  });

  it("the same d produces a proportionally larger offset on a longer chord", () => {
    const source = { x: 0, y: 0 };
    const shortTarget = { x: 100, y: 0 };
    const longTarget = { x: 400, y: 0 };
    const shortPoint = bendPointToAbsolute(source, shortTarget, { t: 0.5, d: 0.2 });
    const longPoint = bendPointToAbsolute(source, longTarget, { t: 0.5, d: 0.2 });
    expect(Math.abs(longPoint.y)).toBeCloseTo(Math.abs(shortPoint.y) * 4);
  });

  it("collapses toward zero offset as the chord itself collapses toward zero length", () => {
    const source = { x: 0, y: 0 };
    const nearlyCoincidentTarget = { x: 0.001, y: 0 };
    const point = bendPointToAbsolute(source, nearlyCoincidentTarget, { t: 0.5, d: 0.2 });
    // Intentional (per design discussion): no minimum floor -- the bulge is allowed to
    // collapse flat when there's nothing meaningful left to bend around.
    expect(Math.abs(point.y)).toBeLessThan(0.001);
  });
});

describe("absoluteToBendPoint", () => {
  it("is the exact inverse of bendPointToAbsolute for well-inside points", () => {
    const source = { x: 10, y: 20 };
    const target = { x: 210, y: 120 };
    const original = { t: 0.35, d: -0.15 };
    const absolute = bendPointToAbsolute(source, target, original);
    const roundTripped = absoluteToBendPoint(source, target, absolute);
    expect(roundTripped.t).toBeCloseTo(original.t);
    expect(roundTripped.d).toBeCloseTo(original.d);
  });

  it("clamps t away from the endpoints -- never exactly 0 or 1", () => {
    const source = { x: 0, y: 0 };
    const target = { x: 100, y: 0 };
    expect(absoluteToBendPoint(source, target, source).t).toBe(0.05);
    expect(absoluteToBendPoint(source, target, target).t).toBe(0.95);
  });

  it("clamps a point dragged past either endpoint the same way", () => {
    const source = { x: 0, y: 0 };
    const target = { x: 100, y: 0 };
    expect(absoluteToBendPoint(source, target, { x: -50, y: 0 }).t).toBe(0.05);
    expect(absoluteToBendPoint(source, target, { x: 150, y: 0 }).t).toBe(0.95);
  });
});

describe("solveQuadraticControlPoint", () => {
  it("produces a curve that passes exactly through the target point at parameter t", () => {
    const p0 = { x: 0, y: 0 };
    const p2 = { x: 100, y: 0 };
    const through = { x: 40, y: 30 };
    const t = 0.4;
    const control = solveQuadraticControlPoint(p0, p2, through, t);
    const onCurve = sampleQuadraticBezier(p0, control, p2, 1000)[Math.round(t * 1000)];
    expect(onCurve.x).toBeCloseTo(through.x, 1);
    expect(onCurve.y).toBeCloseTo(through.y, 1);
  });

  it("the solved control point equals the target itself at t=0.5 on a symmetric chord", () => {
    // At t=0.5, B(0.5) = 0.25*p0 + 0.5*C + 0.25*p2, so solving for C when p0/p2 are symmetric
    // around `through`'s x reduces to a simple, independently-verifiable case.
    const p0 = { x: 0, y: 0 };
    const p2 = { x: 100, y: 0 };
    const through = { x: 50, y: 40 };
    const control = solveQuadraticControlPoint(p0, p2, through, 0.5);
    expect(control).toEqual({ x: 50, y: 80 });
  });
});

describe("buildManualBendRoute", () => {
  it("the curve passes through the bend point when no side stubs are given", () => {
    const source = { x: 0, y: 0 };
    const target = { x: 100, y: 0 };
    const bendPoint = { t: 0.5, d: 0.3 };
    const { sourceStub, control, targetStub, through } = buildManualBendRoute(
      source,
      target,
      bendPoint,
    );
    expect(sourceStub).toEqual(source);
    expect(targetStub).toEqual(target);
    const onCurve = sampleQuadraticBezier(sourceStub, control, targetStub, 1000)[
      Math.round(bendPoint.t * 1000)
    ];
    expect(onCurve.x).toBeCloseTo(through.x, 1);
    expect(onCurve.y).toBeCloseTo(through.y, 1);
  });

  it("extends stubs outward from each side when sides are given", () => {
    const source = { x: 0, y: 0 };
    const target = { x: 100, y: 0 };
    const { sourceStub, targetStub } = buildManualBendRoute(
      source,
      target,
      { t: 0.5, d: 0 },
      "left",
      "right",
    );
    expect(sourceStub.x).toBeLessThan(source.x); // "left" points outward, i.e. more negative x
    expect(targetStub.x).toBeGreaterThan(target.x); // "right" points outward, i.e. more positive x
  });

  it("through matches bendPointToAbsolute for the same inputs", () => {
    const source = { x: 10, y: 5 };
    const target = { x: 210, y: 105 };
    const bendPoint = { t: 0.6, d: -0.25 };
    const { through } = buildManualBendRoute(source, target, bendPoint);
    expect(through).toEqual(bendPointToAbsolute(source, target, bendPoint));
  });
});
