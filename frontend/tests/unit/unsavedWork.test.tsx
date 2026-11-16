import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UnsavedWorkDialog } from "../../src/components/workspace/UnsavedWorkDialog";
import { UnsavedWork, useUnsavedWork } from "../../src/lib/unsavedWork";

/** 025 (FR-017, research R7): unsaved input, and the choice before the agent opens another
 * architecture. */

describe("UnsavedWork", () => {
  it("reports sources while they are dirty", () => {
    const store = new UnsavedWork();
    const { rerender, unmount } = renderHook(
      ({ dirty }) => useUnsavedWork("form", dirty, "the Service tab", () => true, () => {}, store),
      { initialProps: { dirty: false } },
    );
    expect(store.dirty).toBe(false);
    rerender({ dirty: true });
    expect(store.list().map((s) => s.label)).toEqual(["the Service tab"]);
    rerender({ dirty: false });
    expect(store.dirty).toBe(false);
    rerender({ dirty: true });
    unmount();
    expect(store.dirty).toBe(false);
  });

  it("saves every source, and stops at one that fails", async () => {
    const store = new UnsavedWork();
    const first = vi.fn(async () => true);
    const second = vi.fn(async () => false);
    const third = vi.fn(async () => true);
    store.register({ id: "1", label: "a", save: first, discard: vi.fn() });
    store.register({ id: "2", label: "b", save: second, discard: vi.fn() });
    store.register({ id: "3", label: "c", save: third, discard: vi.fn() });
    expect(await store.saveAll()).toBe(false);
    expect(first).toHaveBeenCalled();
    expect(third).not.toHaveBeenCalled();
  });

  it("discards every source and is clean afterwards", () => {
    const store = new UnsavedWork();
    const discard = vi.fn();
    store.register({ id: "1", label: "a", save: () => true, discard });
    store.discardAll();
    expect(discard).toHaveBeenCalled();
    expect(store.dirty).toBe(false);
  });

  it("uses the latest save callback", async () => {
    const store = new UnsavedWork();
    const old = vi.fn(() => true);
    const latest = vi.fn(() => true);
    const { rerender } = renderHook(
      ({ save }) => useUnsavedWork("form", true, "x", save, () => {}, store),
      { initialProps: { save: old } },
    );
    rerender({ save: latest });
    await store.saveAll();
    expect(latest).toHaveBeenCalled();
    expect(old).not.toHaveBeenCalled();
  });
});

describe("UnsavedWorkDialog", () => {
  function renderDialog(onSave = vi.fn(async () => true), onDiscard = vi.fn()) {
    render(
      <UnsavedWorkDialog
        open
        currentName="Prod Web"
        nextName="Staging"
        onSave={onSave}
        onDiscard={onDiscard}
      />,
    );
    return { onSave, onDiscard };
  }

  it("names both architectures and offers only the two choices", () => {
    renderDialog();
    expect(screen.getByText("Unsaved changes in 'Prod Web'")).toBeInTheDocument();
    expect(screen.getByText("The agent is opening 'Staging'.")).toBeInTheDocument();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Discard and continue",
      "Save and continue",
    ]);
  });

  it("ignores Escape", () => {
    const { onSave, onDiscard } = renderDialog();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
    expect(onDiscard).not.toHaveBeenCalled();
  });

  it("discards, or saves", async () => {
    const { onSave, onDiscard } = renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Discard and continue" }));
    expect(onDiscard).toHaveBeenCalled();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    });
    expect(onSave).toHaveBeenCalled();
  });

  it("says when saving failed, and stays", async () => {
    renderDialog(vi.fn(async () => false));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Your changes couldn't be saved.");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
