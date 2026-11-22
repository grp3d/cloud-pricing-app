import { type KeyboardEvent, type ReactNode, useRef } from "react";

import { cn } from "cn";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { HEADER_CONTROL } from "./headerStyles";

/** Marks a menu's top-level items: ArrowUp and ArrowDown move between them. */
export const MENU_ITEM_ATTR = "data-menu-item";

/**
 * 027 (FR-002, research R1, contracts/user-menu-ui.md): the one behaviour both header menus
 * share, so the Cloud Pricing menu and the user menu can't drift apart.
 *
 * - The trigger is a header control; Enter or Space (the button's click) and ArrowDown open the
 *   menu, and Radix focuses its first control.
 * - ArrowUp and ArrowDown move between the elements marked `data-menu-item`, wrapping; a text
 *   field keeps its own arrow keys.
 * - Escape closes the menu and returns focus to the trigger, even after focus has moved into a
 *   nested panel (Radix skips that then, so it's done here). A menu can keep itself open on
 *   Escape by calling `preventDefault` in `onEscapeKeyDown`. Focus stays put when the other
 *   header menu opened while this one was closing.
 */
export function HeaderMenu({
  open,
  onOpenChange,
  trigger,
  triggerLabel,
  triggerClassName,
  contentLabel,
  contentClassName,
  align = "start",
  onEscapeKeyDown,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trigger: ReactNode;
  triggerLabel: string;
  triggerClassName?: string;
  contentLabel: string;
  contentClassName?: string;
  align?: "start" | "center" | "end";
  onEscapeKeyDown?: (event: globalThis.KeyboardEvent) => void;
  children: ReactNode;
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const closedByEscape = useRef(false);

  function onTriggerKeyDown(e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key === "ArrowDown" && !open) {
      e.preventDefault();
      onOpenChange(true);
    }
  }

  function onContentKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const active = document.activeElement;
    if (!(active instanceof HTMLElement) || !active.hasAttribute(MENU_ITEM_ATTR)) return;
    const items = [
      ...e.currentTarget.querySelectorAll<HTMLElement>(`[${MENU_ITEM_ATTR}]:not(:disabled)`),
    ];
    const at = items.indexOf(active);
    if (at < 0 || items.length === 0) return;
    e.preventDefault();
    const step = e.key === "ArrowDown" ? 1 : -1;
    items[(at + step + items.length) % items.length].focus();
  }

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <button
          ref={triggerRef}
          type="button"
          aria-label={triggerLabel}
          className={cn(HEADER_CONTROL, "aria-expanded:bg-header-accent", triggerClassName)}
          onKeyDown={onTriggerKeyDown}
        >
          {trigger}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align={align}
        aria-label={contentLabel}
        className={contentClassName}
        onKeyDown={onContentKeyDown}
        onEscapeKeyDown={(e) => {
          onEscapeKeyDown?.(e);
          if (!e.defaultPrevented) closedByEscape.current = true;
        }}
        ref={contentRef}
        onCloseAutoFocus={(e) => {
          if (!closedByEscape.current) return;
          closedByEscape.current = false;
          e.preventDefault();
          // The other header menu may have opened while this one was closing: leave focus there.
          const active = document.activeElement;
          const inOtherMenu = active?.closest('[data-slot="popover-content"]');
          if (inOtherMenu && inOtherMenu !== contentRef.current) return;
          triggerRef.current?.focus();
        }}
      >
        {children}
      </PopoverContent>
    </Popover>
  );
}
