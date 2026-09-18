import { beforeEach, describe, expect, it, vi } from "vitest";

import { clearConnectorBend, readConnectorBends, writeConnectorBend } from "../../src/lib/connectorBends";

const ARCH_ID = "11111111-1111-1111-1111-111111111111";
const OTHER_ARCH_ID = "22222222-2222-2222-2222-222222222222";

beforeEach(() => {
  localStorage.clear();
});

describe("connectorBends", () => {
  it("returns an empty map when nothing is stored", () => {
    expect(readConnectorBends(ARCH_ID)).toEqual({});
  });

  it("round-trips one Connector's bend", () => {
    writeConnectorBend(ARCH_ID, "conn-1", { controlPoints: [{ t: 0.5, d: 0.2 }] });
    expect(readConnectorBends(ARCH_ID)).toEqual({
      "conn-1": { controlPoints: [{ t: 0.5, d: 0.2 }] },
    });
  });

  it("merges a second Connector's bend without disturbing the first", () => {
    writeConnectorBend(ARCH_ID, "conn-1", { controlPoints: [{ t: 0.5, d: 0.2 }] });
    writeConnectorBend(ARCH_ID, "conn-2", { controlPoints: [{ t: 0.3, d: -0.1 }] });
    expect(readConnectorBends(ARCH_ID)).toEqual({
      "conn-1": { controlPoints: [{ t: 0.5, d: 0.2 }] },
      "conn-2": { controlPoints: [{ t: 0.3, d: -0.1 }] },
    });
  });

  it("overwriting one Connector's entry replaces only that entry", () => {
    writeConnectorBend(ARCH_ID, "conn-1", { controlPoints: [{ t: 0.5, d: 0.2 }] });
    writeConnectorBend(ARCH_ID, "conn-1", { controlPoints: [{ t: 0.8, d: -0.4 }] });
    expect(readConnectorBends(ARCH_ID)).toEqual({
      "conn-1": { controlPoints: [{ t: 0.8, d: -0.4 }] },
    });
  });

  it("scopes bends per-Architecture — a different Architecture id sees nothing", () => {
    writeConnectorBend(ARCH_ID, "conn-1", { controlPoints: [{ t: 0.5, d: 0.2 }] });
    expect(readConnectorBends(OTHER_ARCH_ID)).toEqual({});
  });

  it("clearConnectorBend removes just that entry, leaving the rest", () => {
    writeConnectorBend(ARCH_ID, "conn-1", { controlPoints: [{ t: 0.5, d: 0.2 }] });
    writeConnectorBend(ARCH_ID, "conn-2", { controlPoints: [{ t: 0.3, d: -0.1 }] });
    clearConnectorBend(ARCH_ID, "conn-1");
    expect(readConnectorBends(ARCH_ID)).toEqual({
      "conn-2": { controlPoints: [{ t: 0.3, d: -0.1 }] },
    });
  });

  it("clearConnectorBend on a Connector with no bend is a harmless no-op", () => {
    expect(() => clearConnectorBend(ARCH_ID, "no-such-connector")).not.toThrow();
    expect(readConnectorBends(ARCH_ID)).toEqual({});
  });

  it("ignores malformed stored JSON rather than throwing", () => {
    localStorage.setItem(`cloud-pricing-diagram-connector-bends-${ARCH_ID}`, "not json");
    expect(readConnectorBends(ARCH_ID)).toEqual({});
  });

  it("ignores an entry with an invalid control point, keeping the rest", () => {
    localStorage.setItem(
      `cloud-pricing-diagram-connector-bends-${ARCH_ID}`,
      JSON.stringify({
        "conn-1": { controlPoints: [{ t: "not a number", d: 0.2 }] },
        "conn-2": { controlPoints: [{ t: 0.3, d: -0.1 }] },
      }),
    );
    expect(readConnectorBends(ARCH_ID)).toEqual({
      "conn-2": { controlPoints: [{ t: 0.3, d: -0.1 }] },
    });
  });

  it("ignores an entry with an empty controlPoints array", () => {
    localStorage.setItem(
      `cloud-pricing-diagram-connector-bends-${ARCH_ID}`,
      JSON.stringify({ "conn-1": { controlPoints: [] } }),
    );
    expect(readConnectorBends(ARCH_ID)).toEqual({});
  });

  it("never throws when localStorage.getItem throws — returns an empty map instead", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readConnectorBends(ARCH_ID)).toEqual({});
    spy.mockRestore();
  });

  it("never throws when localStorage.setItem throws — write is a silent no-op", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota exceeded");
    });
    expect(() =>
      writeConnectorBend(ARCH_ID, "conn-1", { controlPoints: [{ t: 0.5, d: 0.2 }] }),
    ).not.toThrow();
    spy.mockRestore();
  });
});
