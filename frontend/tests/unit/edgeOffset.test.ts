import { describe, expect, it } from "vitest";

import { edgeOffsetIndex } from "../../src/lib/edgeOffset";

describe("edgeOffsetIndex", () => {
  it("assigns offset 0 to a single edge between two nodes", () => {
    const result = edgeOffsetIndex([{ id: "e1", source: "a", target: "b" }]);
    expect(result).toEqual({ e1: 0 });
  });

  it("assigns increasing offsets to multiple edges sharing the same source/target pair", () => {
    const result = edgeOffsetIndex([
      { id: "e1", source: "a", target: "b" },
      { id: "e2", source: "a", target: "b" },
      { id: "e3", source: "a", target: "b" },
    ]);
    expect(result).toEqual({ e1: 0, e2: 1, e3: 2 });
  });

  it("treats a pair as order-independent — A->B and B->A share the same group", () => {
    const result = edgeOffsetIndex([
      { id: "e1", source: "a", target: "b" },
      { id: "e2", source: "b", target: "a" },
    ]);
    expect(result).toEqual({ e1: 0, e2: 1 });
  });

  it("does not let edges between distinct pairs affect each other's offset", () => {
    const result = edgeOffsetIndex([
      { id: "e1", source: "a", target: "b" },
      { id: "e2", source: "c", target: "d" },
      { id: "e3", source: "a", target: "b" },
    ]);
    expect(result).toEqual({ e1: 0, e2: 0, e3: 1 });
  });

  it("returns an empty map for no edges", () => {
    expect(edgeOffsetIndex([])).toEqual({});
  });
});
