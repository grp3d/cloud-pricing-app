import { beforeEach, describe, expect, it } from "vitest";

import { readColumnCollapsed, writeColumnCollapsed } from "../../src/lib/columnCollapse";

describe("columnCollapse", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns an empty object when nothing is stored", () => {
    expect(readColumnCollapsed()).toEqual({});
  });

  it("round-trips a written collapsed flag", () => {
    writeColumnCollapsed("collections", true);
    expect(readColumnCollapsed()).toEqual({ collections: true });
  });

  it("round-trips an explicit false (expanded) flag, not just true", () => {
    writeColumnCollapsed("provider", true);
    writeColumnCollapsed("provider", false);
    expect(readColumnCollapsed()).toEqual({ provider: false });
  });

  it("keeps each column's flag independent of the others", () => {
    writeColumnCollapsed("provider", true);
    writeColumnCollapsed("service", false);
    expect(readColumnCollapsed()).toEqual({ provider: true, service: false });
  });

  it("falls back to an empty object for malformed stored data, rather than throwing", () => {
    localStorage.setItem("cloud-pricing-column-collapsed", "not json");
    expect(readColumnCollapsed()).toEqual({});
  });

  it("ignores non-boolean values for a column, keeping the rest", () => {
    localStorage.setItem(
      "cloud-pricing-column-collapsed",
      JSON.stringify({ collections: "yes", service: 1, provider: true }),
    );
    expect(readColumnCollapsed()).toEqual({ provider: true });
  });
});
