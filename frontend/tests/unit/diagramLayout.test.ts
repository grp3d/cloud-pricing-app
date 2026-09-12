import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  readDiagramLayout,
  writeCollectionLayout,
  type CollectionLayoutOverride,
} from "../../src/lib/diagramLayout";

const ARCH_ID = "11111111-1111-1111-1111-111111111111";
const OTHER_ARCH_ID = "22222222-2222-2222-2222-222222222222";

function override(overrides: Partial<CollectionLayoutOverride> = {}): CollectionLayoutOverride {
  return { width: 200, height: 100, x: 10, y: 20, ...overrides };
}

beforeEach(() => {
  localStorage.clear();
});

describe("diagramLayout", () => {
  it("returns an empty layout when nothing is stored", () => {
    expect(readDiagramLayout(ARCH_ID)).toEqual({});
  });

  it("round-trips one Collection's override", () => {
    writeCollectionLayout(ARCH_ID, "collection-1", override());
    expect(readDiagramLayout(ARCH_ID)).toEqual({ "collection-1": override() });
  });

  it("merges a second Collection's override without disturbing the first", () => {
    writeCollectionLayout(ARCH_ID, "collection-1", override({ width: 200 }));
    writeCollectionLayout(ARCH_ID, "collection-2", override({ width: 300 }));
    expect(readDiagramLayout(ARCH_ID)).toEqual({
      "collection-1": override({ width: 200 }),
      "collection-2": override({ width: 300 }),
    });
  });

  it("overwriting one Collection's entry replaces only that entry", () => {
    writeCollectionLayout(ARCH_ID, "collection-1", override({ width: 200 }));
    writeCollectionLayout(ARCH_ID, "collection-1", override({ width: 250 }));
    expect(readDiagramLayout(ARCH_ID)).toEqual({ "collection-1": override({ width: 250 }) });
  });

  it("scopes layout per-Architecture — a different Architecture id sees nothing", () => {
    writeCollectionLayout(ARCH_ID, "collection-1", override());
    expect(readDiagramLayout(OTHER_ARCH_ID)).toEqual({});
  });

  it("never throws when localStorage.getItem throws — returns an empty layout instead", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readDiagramLayout(ARCH_ID)).toEqual({});
    spy.mockRestore();
  });

  it("never throws when localStorage.setItem throws — write is a silent no-op", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota exceeded");
    });
    expect(() => writeCollectionLayout(ARCH_ID, "collection-1", override())).not.toThrow();
    spy.mockRestore();
  });

  it("ignores malformed stored JSON rather than throwing", () => {
    localStorage.setItem(`cloud-pricing-diagram-layout-${ARCH_ID}`, "not json");
    expect(readDiagramLayout(ARCH_ID)).toEqual({});
  });
});
