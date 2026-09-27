import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  readIconLayout,
  removeIconPosition,
  writeIconPosition,
  writeIconPositions,
} from "../../src/lib/iconLayoutStorage";

describe("icon layout storage (016, FR-006)", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("round-trips positions under cloud-pricing-icon-layout-<id>", () => {
    writeIconPosition("A", "s1", { x: 150, y: 0 });
    writeIconPosition("A", "s2", { x: 0, y: 150 });
    expect(localStorage.getItem("cloud-pricing-icon-layout-A")).not.toBeNull();
    expect(readIconLayout("A")).toEqual({ s1: { x: 150, y: 0 }, s2: { x: 0, y: 150 } });
  });

  it("keeps architectures separate", () => {
    writeIconPosition("A", "s1", { x: 1, y: 2 });
    expect(readIconLayout("B")).toEqual({});
  });

  it("drops invalid entries and keeps the rest", () => {
    localStorage.setItem(
      "cloud-pricing-icon-layout-A",
      JSON.stringify({ good: { x: 1, y: 2 }, bad: { x: "1" }, worse: null }),
    );
    expect(readIconLayout("A")).toEqual({ good: { x: 1, y: 2 } });
  });

  it("reads malformed JSON as empty", () => {
    localStorage.setItem("cloud-pricing-icon-layout-A", "{nope");
    expect(readIconLayout("A")).toEqual({});
  });

  it("writes several positions at once, keeping the rest", () => {
    writeIconPosition("A", "s1", { x: 1, y: 2 });
    writeIconPositions("A", { s2: { x: 3, y: 4 }, s3: { x: 5, y: 6 } });
    expect(readIconLayout("A")).toEqual({
      s1: { x: 1, y: 2 },
      s2: { x: 3, y: 4 },
      s3: { x: 5, y: 6 },
    });
  });

  it("removes one position", () => {
    writeIconPosition("A", "s1", { x: 1, y: 2 });
    writeIconPosition("A", "s2", { x: 3, y: 4 });
    removeIconPosition("A", "s1");
    expect(readIconLayout("A")).toEqual({ s2: { x: 3, y: 4 } });
  });

  it("never throws when storage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readIconLayout("A")).toEqual({});
    expect(() => writeIconPosition("A", "s1", { x: 0, y: 0 })).not.toThrow();
    expect(() => removeIconPosition("A", "s1")).not.toThrow();
  });
});
