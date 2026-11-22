import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { HeaderMenu } from "../../src/components/layout/HeaderMenu";

/** 027 (FR-002, contracts/user-menu-ui.md "Keyboard"): the behaviour both header menus share. */

function Harness({ keepOpenOnEscape = false }: { keepOpenOnEscape?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <HeaderMenu
      open={open}
      onOpenChange={setOpen}
      triggerLabel="Test menu"
      trigger={<span>T</span>}
      contentLabel="Test items"
      onEscapeKeyDown={keepOpenOnEscape ? (e) => e.preventDefault() : undefined}
    >
      <button type="button" data-menu-item>
        One
      </button>
      <input aria-label="A field" />
      <button type="button" data-menu-item>
        Two
      </button>
      <button type="button" data-menu-item>
        Three
      </button>
    </HeaderMenu>
  );
}

const trigger = () => screen.getByRole("button", { name: "Test menu" });
const item = (name: string) => screen.getByRole("button", { name });

describe("HeaderMenu", () => {
  it.each(["Enter", " ", "ArrowDown"])("opens with %j and focuses the first item", async (key) => {
    render(<Harness />);
    trigger().focus();
    expect(trigger()).toHaveAttribute("aria-expanded", "false");
    fireEvent.keyDown(trigger(), { key });
    if (key !== "ArrowDown") fireEvent.click(trigger()); // a browser clicks a button on Enter/Space
    expect(await screen.findByRole("dialog", { name: "Test items" })).toBeInTheDocument();
    expect(trigger()).toHaveAttribute("aria-expanded", "true");
    expect(item("One")).toHaveFocus();
  });

  it("moves between items with ArrowDown and ArrowUp, wrapping, and skips other controls", async () => {
    render(<Harness />);
    fireEvent.keyDown(trigger(), { key: "ArrowDown" });
    await screen.findByRole("dialog");
    expect(item("One")).toHaveFocus();
    fireEvent.keyDown(item("One"), { key: "ArrowDown" });
    expect(item("Two")).toHaveFocus();
    fireEvent.keyDown(item("Two"), { key: "ArrowDown" });
    expect(item("Three")).toHaveFocus();
    fireEvent.keyDown(item("Three"), { key: "ArrowDown" });
    expect(item("One")).toHaveFocus();
    fireEvent.keyDown(item("One"), { key: "ArrowUp" });
    expect(item("Three")).toHaveFocus();
  });

  it("leaves arrow keys alone in a text field", async () => {
    render(<Harness />);
    fireEvent.keyDown(trigger(), { key: "ArrowDown" });
    await screen.findByRole("dialog");
    const field = screen.getByRole("textbox", { name: "A field" });
    field.focus();
    fireEvent.keyDown(field, { key: "ArrowDown" });
    expect(field).toHaveFocus();
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    render(<Harness />);
    fireEvent.keyDown(trigger(), { key: "ArrowDown" });
    await screen.findByRole("dialog");
    fireEvent.keyDown(item("Two"), { key: "ArrowDown" });
    fireEvent.keyDown(document.activeElement as Element, { key: "Escape" });
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // Radix returns focus after its unmount tick.
    await vi.waitFor(() => expect(trigger()).toHaveFocus());
    expect(trigger()).toHaveAttribute("aria-expanded", "false");
  });

  it("stays open when the menu's own Escape handler prevents it", async () => {
    render(<Harness keepOpenOnEscape />);
    fireEvent.keyDown(trigger(), { key: "ArrowDown" });
    await screen.findByRole("dialog");
    fireEvent.keyDown(item("One"), { key: "Escape" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
