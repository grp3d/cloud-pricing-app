import { beforeEach, describe, expect, it } from "vitest";

import { readColumnWidths, writeColumnWidth } from "../../src/lib/columnWidths";

describe("columnWidths", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns an empty object when nothing is stored", () => {
    expect(readColumnWidths()).toEqual({});
  });

  it("round-trips a written width", () => {
    writeColumnWidth("collections", 400);
    expect(readColumnWidths()).toEqual({ collections: 400 });
  });

  it("keeps each column's width independent of the others", () => {
    writeColumnWidth("collections", 400);
    writeColumnWidth("service", 350);
    expect(readColumnWidths()).toEqual({ collections: 400, service: 350 });
  });

  it("falls back to an empty object for malformed stored data, rather than throwing", () => {
    localStorage.setItem("cloud-pricing-column-widths", "not json");
    expect(readColumnWidths()).toEqual({});
  });

  it("ignores non-numeric or non-positive values for a column, keeping the rest", () => {
    localStorage.setItem(
      "cloud-pricing-column-widths",
      JSON.stringify({ collections: "wide", service: -5, pricing: 300 }),
    );
    expect(readColumnWidths()).toEqual({ pricing: 300 });
  });
});
