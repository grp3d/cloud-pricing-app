import { describe, expect, it } from "vitest";

import { canConnect } from "../../src/pages/connectorSelection";

describe("canConnect", () => {
  it("is false with zero selected boxes", () => {
    expect(canConnect([])).toBe(false);
  });

  it("is false with one selected box", () => {
    expect(canConnect(["a"])).toBe(false);
  });

  it("is true with exactly two selected boxes", () => {
    expect(canConnect(["a", "b"])).toBe(true);
  });

  it("is false with three or more selected boxes", () => {
    expect(canConnect(["a", "b", "c"])).toBe(false);
  });
});
