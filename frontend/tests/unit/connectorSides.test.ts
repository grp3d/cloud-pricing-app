import { beforeEach, describe, expect, it, vi } from "vitest";

import { readConnectorSides, writeConnectorSides } from "../../src/lib/connectorSides";

const ARCH_ID = "11111111-1111-1111-1111-111111111111";
const OTHER_ARCH_ID = "22222222-2222-2222-2222-222222222222";

beforeEach(() => {
  localStorage.clear();
});

describe("connectorSides", () => {
  it("returns an empty map when nothing is stored", () => {
    expect(readConnectorSides(ARCH_ID)).toEqual({});
  });

  it("round-trips one Connector's sides", () => {
    writeConnectorSides(ARCH_ID, "conn-1", { from: "right", to: "left" });
    expect(readConnectorSides(ARCH_ID)).toEqual({ "conn-1": { from: "right", to: "left" } });
  });

  it("merges a second Connector's sides without disturbing the first", () => {
    writeConnectorSides(ARCH_ID, "conn-1", { from: "right", to: "left" });
    writeConnectorSides(ARCH_ID, "conn-2", { from: "top", to: "bottom" });
    expect(readConnectorSides(ARCH_ID)).toEqual({
      "conn-1": { from: "right", to: "left" },
      "conn-2": { from: "top", to: "bottom" },
    });
  });

  it("overwriting one Connector's entry replaces only that entry", () => {
    writeConnectorSides(ARCH_ID, "conn-1", { from: "right", to: "left" });
    writeConnectorSides(ARCH_ID, "conn-1", { from: "bottom", to: "top" });
    expect(readConnectorSides(ARCH_ID)).toEqual({ "conn-1": { from: "bottom", to: "top" } });
  });

  it("scopes sides per-Architecture — a different Architecture id sees nothing", () => {
    writeConnectorSides(ARCH_ID, "conn-1", { from: "right", to: "left" });
    expect(readConnectorSides(OTHER_ARCH_ID)).toEqual({});
  });

  it("ignores malformed stored JSON rather than throwing", () => {
    localStorage.setItem(`cloud-pricing-diagram-connector-sides-${ARCH_ID}`, "not json");
    expect(readConnectorSides(ARCH_ID)).toEqual({});
  });

  it("ignores an entry with an invalid side value, keeping the rest", () => {
    localStorage.setItem(
      `cloud-pricing-diagram-connector-sides-${ARCH_ID}`,
      JSON.stringify({
        "conn-1": { from: "diagonal", to: "left" },
        "conn-2": { from: "top", to: "bottom" },
      }),
    );
    expect(readConnectorSides(ARCH_ID)).toEqual({ "conn-2": { from: "top", to: "bottom" } });
  });

  it("never throws when localStorage.getItem throws — returns an empty map instead", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readConnectorSides(ARCH_ID)).toEqual({});
    spy.mockRestore();
  });

  it("never throws when localStorage.setItem throws — write is a silent no-op", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota exceeded");
    });
    expect(() =>
      writeConnectorSides(ARCH_ID, "conn-1", { from: "right", to: "left" }),
    ).not.toThrow();
    spy.mockRestore();
  });
});
