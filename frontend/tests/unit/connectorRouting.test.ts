import { describe, expect, it } from "vitest";

import { chooseConnectorSides, type ConnectorSide, type Rect } from "../../src/lib/connectorRouting";

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
