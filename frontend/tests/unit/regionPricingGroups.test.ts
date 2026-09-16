import { describe, expect, it } from "vitest";

import { groupLineItemsByRegion } from "../../src/lib/regionPricingGroups";

interface Item {
  id: string;
  price: string;
  region: string | null;
}

function item(id: string, price: string, region: string | null): Item {
  return { id, price, region };
}

describe("groupLineItemsByRegion", () => {
  it("returns one group per distinct region", () => {
    const groups = groupLineItemsByRegion([
      item("a", "10", "us-east-1"),
      item("b", "5", "eu-west-1"),
    ]);
    expect(groups.map((g) => g.region).sort()).toEqual(["eu-west-1", "us-east-1"]);
  });

  it("orders regions by their highest-priced item, matching the overall price-descending order", () => {
    const groups = groupLineItemsByRegion([
      item("a", "5", "eu-west-1"),
      item("b", "10", "us-east-1"),
      item("c", "3", "eu-west-1"),
    ]);
    expect(groups.map((g) => g.region)).toEqual(["us-east-1", "eu-west-1"]);
  });

  it("preserves price-descending order for items within a region", () => {
    const groups = groupLineItemsByRegion([
      item("a", "3", "us-east-1"),
      item("b", "10", "us-east-1"),
      item("c", "7", "us-east-1"),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].items.map((i) => i.id)).toEqual(["b", "c", "a"]);
  });

  it("computes each region's subtotal as the sum of its own items", () => {
    const groups = groupLineItemsByRegion([
      item("a", "10.50", "us-east-1"),
      item("b", "5.25", "us-east-1"),
      item("c", "2", "eu-west-1"),
    ]);
    const usEast = groups.find((g) => g.region === "us-east-1")!;
    const euWest = groups.find((g) => g.region === "eu-west-1")!;
    expect(usEast.subtotal).toBeCloseTo(15.75);
    expect(euWest.subtotal).toBe(2);
  });

  it("groups items with no determinable region under 'Global' (spec FR-015 defensive fallback)", () => {
    const groups = groupLineItemsByRegion([item("a", "10", null), item("b", "5", "us-east-1")]);
    expect(groups.map((g) => g.region)).toContain("Global");
    const global = groups.find((g) => g.region === "Global")!;
    expect(global.items.map((i) => i.id)).toEqual(["a"]);
  });

  it("still returns a single labeled, subtotaled section when only one region is present", () => {
    const groups = groupLineItemsByRegion([
      item("a", "10", "us-east-1"),
      item("b", "5", "us-east-1"),
    ]);
    expect(groups).toEqual([
      { region: "us-east-1", items: [item("a", "10", "us-east-1"), item("b", "5", "us-east-1")], subtotal: 15 },
    ]);
  });

  it("returns an empty array for an empty input", () => {
    expect(groupLineItemsByRegion([])).toEqual([]);
  });
});
