import { describe, expect, it } from "vitest";

import { updateOrderedSelection } from "../../src/pages/connectorSelection";

// --- 010-multi-region-support, spec FR-008: click order, not React Flow's array order ---

describe("updateOrderedSelection", () => {
  it("starts fresh from an empty previous order", () => {
    expect(updateOrderedSelection([], ["a"])).toEqual(["a"]);
  });

  it("appends a newly-selected id after already-selected ones, regardless of the current array's own order", () => {
    // React Flow reports "b" before "a" here (its own internal order) — "a" was clicked
    // first, so it must stay first.
    expect(updateOrderedSelection(["a"], ["b", "a"])).toEqual(["a", "b"]);
  });

  it("drops an id that's no longer selected, preserving the remaining order", () => {
    expect(updateOrderedSelection(["a", "b"], ["b"])).toEqual(["b"]);
  });

  it("replaces a deselected id with a newly-selected one, remaining id keeps its position", () => {
    // "a" deselected, "c" newly selected — "b" (still selected) stays first.
    expect(updateOrderedSelection(["a", "b"], ["c", "b"])).toEqual(["b", "c"]);
  });

  it("returns an empty array when nothing is selected", () => {
    expect(updateOrderedSelection(["a", "b"], [])).toEqual([]);
  });

  it("is a no-op when the selected set is unchanged", () => {
    expect(updateOrderedSelection(["a", "b"], ["b", "a"])).toEqual(["a", "b"]);
  });
});
