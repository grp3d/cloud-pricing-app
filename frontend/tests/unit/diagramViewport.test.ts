import { beforeEach, describe, expect, it, vi } from "vitest";

import { readDiagramZoom, writeDiagramZoom } from "../../src/lib/diagramViewport";

const ARCH_ID = "11111111-1111-1111-1111-111111111111";
const OTHER_ARCH_ID = "22222222-2222-2222-2222-222222222222";

beforeEach(() => {
  localStorage.clear();
});

describe("diagramViewport", () => {
  it("returns null when nothing is stored", () => {
    expect(readDiagramZoom(ARCH_ID)).toBeNull();
  });

  it("round-trips a written zoom level", () => {
    writeDiagramZoom(ARCH_ID, 1.5);
    expect(readDiagramZoom(ARCH_ID)).toBe(1.5);
  });

  it("overwriting replaces the prior value", () => {
    writeDiagramZoom(ARCH_ID, 1.5);
    writeDiagramZoom(ARCH_ID, 0.75);
    expect(readDiagramZoom(ARCH_ID)).toBe(0.75);
  });

  it("scopes zoom per-Architecture — a different Architecture id sees nothing", () => {
    writeDiagramZoom(ARCH_ID, 1.5);
    expect(readDiagramZoom(OTHER_ARCH_ID)).toBeNull();
  });

  it("ignores malformed stored JSON rather than throwing", () => {
    localStorage.setItem(`cloud-pricing-diagram-zoom-${ARCH_ID}`, "not json");
    expect(readDiagramZoom(ARCH_ID)).toBeNull();
  });

  it("ignores an out-of-range stored value rather than returning nonsense", () => {
    localStorage.setItem(`cloud-pricing-diagram-zoom-${ARCH_ID}`, "0");
    expect(readDiagramZoom(ARCH_ID)).toBeNull();
    localStorage.setItem(`cloud-pricing-diagram-zoom-${ARCH_ID}`, "1000");
    expect(readDiagramZoom(ARCH_ID)).toBeNull();
  });

  it("never throws when localStorage.getItem throws — returns null instead", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readDiagramZoom(ARCH_ID)).toBeNull();
    spy.mockRestore();
  });

  it("never throws when localStorage.setItem throws — write is a silent no-op", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota exceeded");
    });
    expect(() => writeDiagramZoom(ARCH_ID, 1.5)).not.toThrow();
    spy.mockRestore();
  });
});
