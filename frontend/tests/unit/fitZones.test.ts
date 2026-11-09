import { describe, expect, it } from "vitest";

import { CANVAS_MIN_WIDTH, fitZones } from "../../src/lib/fitZones";

/** 021 research R4: the rendered widths of the sidebar, canvas and inspector. */

const zones = (
  sidebar = 320,
  inspector = 360,
  sidebarCollapsed = false,
  inspectorCollapsed = false,
) => ({
  sidebar,
  inspector,
  sidebarCollapsed,
  inspectorCollapsed,
});

describe("fitZones", () => {
  it("gives the canvas what is left at the default widths", () => {
    expect(fitZones(1280, zones())).toEqual({ sidebar: 320, canvas: 600, inspector: 360 });
    expect(fitZones(1600, zones())).toEqual({ sidebar: 320, canvas: 920, inspector: 360 });
  });

  it("keeps the canvas at 400px by shrinking the sidebar first", () => {
    // 1000 - 400 = 600 for both zones; the inspector keeps 360, the sidebar gets 240.
    expect(fitZones(1000, zones())).toEqual({ sidebar: 240, canvas: 400, inspector: 360 });
  });

  it("then shrinks the inspector, each to no less than 56px", () => {
    // 700 - 400 = 300: the sidebar goes to its 56px rail, the inspector gets 244.
    expect(fitZones(700, zones())).toEqual({ sidebar: 56, canvas: 400, inspector: 244 });
    // 500 - 400 = 100: both at their rails would need 112, so the canvas gives up the rest.
    expect(fitZones(500, zones())).toEqual({ sidebar: 56, canvas: 388, inspector: 56 });
  });

  it("counts a collapsed zone as its 56px rail", () => {
    expect(fitZones(1280, zones(320, 360, true, false))).toEqual({
      sidebar: 56,
      canvas: 864,
      inspector: 360,
    });
    expect(fitZones(1280, zones(320, 360, true, true))).toEqual({
      sidebar: 56,
      canvas: 1168,
      inspector: 56,
    });
  });

  it("never returns a negative canvas", () => {
    expect(fitZones(80, zones()).canvas).toBe(0);
    expect(fitZones(0, zones())).toEqual({ sidebar: 56, canvas: 0, inspector: 56 });
  });

  it("does not change the saved widths it is given", () => {
    const input = zones();
    const copy = { ...input };
    fitZones(700, input);
    expect(input).toEqual(copy);
  });

  it("uses a 400px canvas minimum", () => {
    expect(CANVAS_MIN_WIDTH).toBe(400);
  });
});
