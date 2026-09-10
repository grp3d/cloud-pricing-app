import { describe, expect, it } from "vitest";

import {
  existingServiceSelection,
  newServiceSelection,
} from "../../src/lib/serviceConfigSelection";

describe("serviceConfigSelection", () => {
  it("existingServiceSelection() builds an 'existing' selection for an already-added SKU Selection", () => {
    expect(existingServiceSelection("sel-1")).toEqual({
      kind: "existing",
      skuSelectionId: "sel-1",
    });
  });

  it("newServiceSelection() builds a 'new' selection for a picked-but-not-yet-added catalog SKU", () => {
    const catalogSku = { service_code: "AmazonEC2", sku: "SKU1" } as never;
    expect(newServiceSelection(catalogSku)).toEqual({
      kind: "new",
      catalogSku,
    });
  });

  // 007-ui-overhaul-shadcn, FR-015: a single ServiceConfigSelection slot (not two separate
  // pieces of state, as before this feature) makes "at most one service's configuration at a
  // time, selecting a different one replaces it" structural rather than a convention two
  // states have to be kept in sync to honor — there is no separate "clear the other one"
  // step, since assigning a new selection is the only way to change it.
  it("both constructors produce values of the same ServiceConfigSelection type, so assigning either one is a full replacement, never a merge", () => {
    const a = existingServiceSelection("sel-1");
    const b = newServiceSelection({ service_code: "AmazonEC2", sku: "SKU2" } as never);
    // No property from `a` leaks into `b` — they're independent values of a discriminated
    // union, not two properties of one merged object.
    expect(Object.keys(a)).not.toEqual(expect.arrayContaining(["catalogSku"]));
    expect(Object.keys(b)).not.toEqual(expect.arrayContaining(["skuSelectionId"]));
  });
});
