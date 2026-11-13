import { describe, expect, it } from "vitest";

import { DEFAULT_CENTER, nextCenter, readCenter } from "../../src/lib/centerLayout";

describe("centre column layout (023)", () => {
  it("starts merged with the Canvas in front", () => {
    expect(readCenter(null)).toEqual(DEFAULT_CENTER);
    expect(DEFAULT_CENTER).toMatchObject({ mode: "merged", front: "canvas" });
  });

  it("reads a saved arrangement and ignores an invalid one", () => {
    const saved = { mode: "split", upper: "agent", front: "canvas", split: 0.3 } as const;
    expect(readCenter({ center: saved })).toEqual(saved);
    expect(
      readCenter({ center: { ...saved, upper: "pricing" } as unknown as typeof saved }),
    ).toEqual(DEFAULT_CENTER);
  });

  it("moves Agent to the lower half, swaps, and merges back with the chosen tab in front", () => {
    const split = nextCenter(DEFAULT_CENTER, { type: "drop-on-lower", tab: "agent" });
    expect(split).toMatchObject({ mode: "split", upper: "canvas" });
    const swapped = nextCenter(split, { type: "swap" });
    expect(swapped.upper).toBe("agent");
    expect(nextCenter(swapped, { type: "merge", tab: "agent" })).toMatchObject({
      mode: "merged",
      front: "agent",
    });
  });
});
