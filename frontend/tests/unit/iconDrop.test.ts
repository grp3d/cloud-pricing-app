import { describe, expect, it } from "vitest";

import { decideIconDrop, type DropBox } from "../../src/lib/iconDrop";

// A us-east-1 VPC containing a nested Application, a second us-east-1 Application beside it,
// and a us-west-2 VPC further right. Rects are absolute flow coordinates.
const boxes: DropBox[] = [
  { id: "vpc", region: "us-east-1", rect: { x: 0, y: 0, width: 400, height: 400 } },
  {
    id: "nested",
    parentId: "vpc",
    region: "us-east-1",
    rect: { x: 20, y: 200, width: 200, height: 150 },
  },
  { id: "app", region: "us-east-1", rect: { x: 500, y: 0, width: 200, height: 200 } },
  { id: "west", region: "us-west-2", rect: { x: 800, y: 0, width: 300, height: 300 } },
];

describe("decideIconDrop (016, FR-004–FR-004b)", () => {
  it("does nothing on empty canvas", () => {
    expect(decideIconDrop({ point: { x: 450, y: 600 }, boxes, sourceId: "vpc" })).toEqual({
      kind: "none",
    });
  });

  it("keeps a drop inside the source box as a same-box move", () => {
    expect(decideIconDrop({ point: { x: 100, y: 50 }, boxes, sourceId: "vpc" })).toEqual({
      kind: "same-box",
      targetId: "vpc",
    });
  });

  it("prefers a nested box over the VPC that contains it", () => {
    expect(decideIconDrop({ point: { x: 100, y: 250 }, boxes, sourceId: "vpc" })).toEqual({
      kind: "move",
      targetId: "nested",
    });
  });

  it("moves into the parent VPC from a nested box when dropped outside the nested box", () => {
    expect(decideIconDrop({ point: { x: 300, y: 50 }, boxes, sourceId: "nested" })).toEqual({
      kind: "move",
      targetId: "vpc",
    });
  });

  it("moves into another same-region box", () => {
    expect(decideIconDrop({ point: { x: 600, y: 100 }, boxes, sourceId: "vpc" })).toEqual({
      kind: "move",
      targetId: "app",
    });
  });

  it("rejects a drop into a box in another region, naming the source region", () => {
    expect(decideIconDrop({ point: { x: 900, y: 100 }, boxes, sourceId: "vpc" })).toEqual({
      kind: "reject-region",
      sourceRegion: "us-east-1",
    });
  });

  it("does nothing if the source box is unknown", () => {
    expect(decideIconDrop({ point: { x: 100, y: 50 }, boxes, sourceId: "gone" })).toEqual({
      kind: "none",
    });
  });
});
