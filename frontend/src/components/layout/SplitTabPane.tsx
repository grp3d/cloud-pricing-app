import { MoreHorizontal } from "lucide-react";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";

import {
  SPLIT_MAX,
  SPLIT_MIN,
  type TabAction,
  type TabArrangement,
  type TabPair,
  otherTab,
} from "../../lib/tabArrangement";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

/** A drag starts only after this much pointer movement, so a click still selects the tab. */
const DRAG_THRESHOLD_PX = 4;

type DropZone = "upper-bar" | "lower-half" | null;

export interface SplitTabPaneProps<T extends string> {
  tabs: TabPair<T>;
  labels: Record<T, string>;
  bodies: Record<T, ReactNode>;
  arrangement: TabArrangement<T>;
  onAction: (action: TabAction<T>) => void;
  /** Names the pane for assistive tech, in lower case: "inspector" gives "Inspector tabs",
   * "Upper inspector pane", "Resize inspector panes". */
  name: string;
  /** Hidden (the inspector collapsed to its rail): the bodies stay mounted. */
  hidden?: boolean;
  /** Extra controls at the end of the upper tab bar. */
  barEnd?: ReactNode;
  /** Shown in the middle of the upper tab bar (the open architecture's name): centred when
   * there's room, never over the tabs. */
  barCenter?: ReactNode;
  /** A tab that's shown but can't be opened, with the reason as its tooltip. While a tab is
   * inactive, the tabs can't be moved, split or merged, so the caller shows a merged
   * arrangement with the other tab in front. */
  inactive?: Partial<Record<T, string>>;
  /** Keep a hidden body laid out at full size, just invisible, instead of removing it from
   * the layout; for a body that measures itself (the canvas), so it keeps its view. */
  keepHiddenSized?: boolean;
  /** Scroll the pane as a whole (the inspector) rather than leave it to each body. */
  scrollable?: boolean;
}

/**
 * Two tabs that share one pane or split it (021's inspector, generalised in 023 for the centre
 * column's Canvas and Agent tabs).
 *
 * - **Merged:** one pane, one visible tab.
 * - **Split:** an upper and a lower pane, one tab each, with a draggable divider. Tabs are
 *   dragged with pointer events to the lower half (split or swap) or onto the upper tab bar
 *   (merge); each pane's tab options menu does the same from the keyboard. Escape or a drop
 *   elsewhere cancels.
 *
 * Both bodies stay mounted in one parent in every arrangement (shown or hidden, and placed with
 * CSS `order`), so their state survives tab switches, splits, merges and swaps. The tabs are
 * therefore written with the ARIA tab roles directly rather than with a Tabs component, which
 * would re-parent the bodies on every split or merge. Every arrangement change goes through
 * `onAction`.
 */
export function SplitTabPane<T extends string>({
  tabs,
  labels,
  bodies,
  arrangement,
  onAction,
  name,
  hidden = false,
  barEnd,
  barCenter,
  inactive,
  keepHiddenSized = false,
  scrollable = false,
}: SplitTabPaneProps<T>) {
  const idBase = useId();
  const tabId = (t: T) => `${idBase}-tab-${t}`;
  const panelId = (t: T) => `${idBase}-panel-${t}`;
  const other = (t: T) => otherTab(tabs, t);
  const locked = Boolean(inactive && tabs.some((t) => inactive[t]));
  const split = arrangement.mode === "split";
  const upper = split ? arrangement.upper : arrangement.front;
  const lower = other(arrangement.upper);
  const title = name.charAt(0).toUpperCase() + name.slice(1);

  const containerRef = useRef<HTMLDivElement>(null);
  const upperBarRef = useRef<HTMLDivElement>(null);

  // --- Divider: live while dragging, saved on release. ---
  const [liveSplit, setLiveSplit] = useState<number | null>(null);
  const shownSplit = liveSplit ?? arrangement.split;

  // --- Tab drag. ---
  const [drag, setDrag] = useState<{ tab: T; zone: DropZone } | null>(null);
  const dragCleanupRef = useRef<(() => void) | null>(null);
  useEffect(() => () => dragCleanupRef.current?.(), []);

  function zoneAt(clientY: number): DropZone {
    const container = containerRef.current?.getBoundingClientRect();
    const bar = upperBarRef.current?.getBoundingClientRect();
    if (!container) return null;
    if (bar && clientY >= bar.top && clientY <= bar.bottom) return "upper-bar";
    if (clientY >= container.top + container.height / 2 && clientY <= container.bottom) {
      return "lower-half";
    }
    return null;
  }

  function startTabPointer(tab: T, e: React.PointerEvent<HTMLButtonElement>) {
    if (e.button !== 0 || locked) return;
    const startX = e.clientX;
    const startY = e.clientY;
    const target = e.currentTarget;
    let dragging = false;
    let zone: DropZone = null;

    const finish = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("keydown", onKey, true);
      if (target.hasPointerCapture?.(e.pointerId)) target.releasePointerCapture(e.pointerId);
      dragCleanupRef.current = null;
      setDrag(null);
    };
    const onMove = (ev: PointerEvent) => {
      if (!dragging) {
        if (Math.hypot(ev.clientX - startX, ev.clientY - startY) < DRAG_THRESHOLD_PX) return;
        dragging = true;
        target.setPointerCapture?.(e.pointerId);
      }
      zone = zoneAt(ev.clientY);
      setDrag({ tab, zone });
    };
    const onUp = () => {
      const wasDragging = dragging;
      const dropZone = zone;
      finish();
      if (!wasDragging) return;
      if (dropZone === "lower-half") onAction({ type: "drop-on-lower", tab });
      else if (dropZone === "upper-bar") onAction({ type: "drop-on-upper-bar", tab });
    };
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape" && dragging) {
        ev.preventDefault();
        ev.stopPropagation();
        finish();
      }
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("keydown", onKey, true);
    dragCleanupRef.current = finish;
  }

  function tabButton(tab: T, inMergedBar: boolean) {
    const reason = inactive?.[tab];
    if (reason) {
      return (
        <Tooltip key={tab}>
          <TooltipTrigger asChild>
            <button
              id={tabId(tab)}
              type="button"
              role="tab"
              aria-selected={false}
              aria-disabled
              aria-controls={panelId(tab)}
              tabIndex={-1}
              className="h-7 cursor-not-allowed rounded-md px-2.5 text-xs font-medium text-muted-foreground/60"
            >
              {labels[tab]}
            </button>
          </TooltipTrigger>
          <TooltipContent>{reason}</TooltipContent>
        </Tooltip>
      );
    }
    const selected = inMergedBar ? arrangement.front === tab : true;
    return (
      <button
        key={tab}
        id={tabId(tab)}
        type="button"
        role="tab"
        aria-selected={selected}
        aria-controls={panelId(tab)}
        tabIndex={selected ? 0 : -1}
        className={`focus-ring relative h-7 rounded-md px-2.5 text-xs font-medium transition-colors ${
          locked ? "" : "cursor-grab active:cursor-grabbing"
        } ${
          selected
            ? "bg-background text-foreground shadow-xs"
            : "text-muted-foreground hover:bg-accent hover:text-foreground"
        } ${drag?.tab === tab ? "opacity-60" : ""}`}
        onClick={() => onAction({ type: "select-tab", tab })}
        onKeyDown={(e) => {
          if (!inMergedBar || locked) return;
          if (
            e.key === "ArrowRight" ||
            e.key === "ArrowLeft" ||
            e.key === "Home" ||
            e.key === "End"
          ) {
            e.preventDefault();
            const next = other(tab);
            onAction({ type: "select-tab", tab: next });
            document.getElementById(tabId(next))?.focus();
          }
        }}
        onPointerDown={(e) => startTabPointer(tab, e)}
      >
        {labels[tab]}
      </button>
    );
  }

  function optionsMenu(tab: T) {
    if (locked) return null;
    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-xs" aria-label={`${labels[tab]} tab options`}>
            <MoreHorizontal />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          {split ? (
            <>
              <DropdownMenuItem onSelect={() => onAction({ type: "merge", tab })}>
                Merge
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => onAction({ type: "swap" })}>Swap</DropdownMenuItem>
            </>
          ) : (
            <DropdownMenuItem onSelect={() => onAction({ type: "drop-on-lower", tab })}>
              Move to lower half
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  function startDivider(e: React.PointerEvent<HTMLDivElement>) {
    e.preventDefault();
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect || rect.height <= 0) return;
    const target = e.currentTarget;
    target.setPointerCapture?.(e.pointerId);
    const ratioAt = (clientY: number) =>
      Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, (clientY - rect.top) / rect.height));
    let latest = arrangement.split;
    const onMove = (ev: PointerEvent) => {
      latest = ratioAt(ev.clientY);
      setLiveSplit(latest);
    };
    const onUp = () => {
      target.removeEventListener("pointermove", onMove);
      target.removeEventListener("pointerup", onUp);
      setLiveSplit(null);
      onAction({ type: "set-split", split: latest });
    };
    target.addEventListener("pointermove", onMove);
    target.addEventListener("pointerup", onUp);
  }

  // Bodies are keyed and stay in this one parent; `order` places them.
  function body(tab: T) {
    const visible = !hidden && (split || arrangement.front === tab);
    const isUpper = tab === upper;
    const keepSized = keepHiddenSized && !visible && !hidden;
    // Transparent and behind the visible pane, not `visibility: hidden`: React Flow sets its
    // own nodes and panels visible, which would show through.
    const style: React.CSSProperties = keepSized
      ? { position: "absolute", inset: 0, opacity: 0, zIndex: -1, pointerEvents: "none" }
      : split
        ? {
            order: isUpper ? 1 : 4,
            flex: `${isUpper ? shownSplit : 1 - shownSplit} 1 0px`,
            minHeight: 120,
          }
        : { order: 1, flex: "1 1 0px" };
    return (
      <div
        key={tab}
        id={panelId(tab)}
        role="tabpanel"
        aria-labelledby={tabId(tab)}
        hidden={!visible && !keepSized}
        aria-hidden={keepSized || undefined}
        // Nothing in a hidden body can be clicked or focused (React 18 has no `inert` prop).
        ref={(element) => {
          if (element) element.inert = keepSized;
        }}
        // Pane heights ease over 150ms on split, merge, swap and keyboard resizes; not while
        // the divider is being dragged, where they follow the pointer.
        className={`flex min-h-0 flex-col overflow-hidden ${
          split && liveSplit === null ? "transition-[flex-grow] duration-150 ease-out" : ""
        }`}
        style={style}
      >
        {bodies[tab]}
      </div>
    );
  }

  const upperTabs = (
    <div
      role="tablist"
      aria-label={split ? `Upper ${name} pane` : `${title} tabs`}
      className="flex items-center gap-0.5 rounded-lg bg-muted p-0.5"
    >
      {split ? tabButton(upper, false) : tabs.map((t) => tabButton(t, true))}
    </div>
  );

  const zoneClass = (zone: Exclude<DropZone, null>) =>
    drag?.zone === zone ? "border-primary bg-primary/10" : "border-border bg-muted/40";

  return (
    <div
      ref={containerRef}
      hidden={hidden}
      className={`relative isolate flex min-h-0 flex-1 flex-col ${
        scrollable ? "overflow-y-auto" : "overflow-hidden"
      }`}
    >
      {!hidden && (
        <div
          key="bar-upper"
          ref={upperBarRef}
          // With a centred item: three columns. The side columns share the spare width equally
          // (so the middle is centred) but the left one never gets narrower than the tabs.
          className={`shrink-0 items-center gap-1 border-b border-border bg-muted/40 px-1.5 py-1 ${
            barCenter
              ? "grid grid-cols-[minmax(max-content,1fr)_minmax(0,max-content)_minmax(0,1fr)]"
              : "flex"
          }`}
          style={{ order: 0 }}
        >
          {barCenter ? (
            <>
              <div className="flex items-center gap-1">
                {upperTabs}
                {optionsMenu(upper)}
              </div>
              {barCenter}
              <div className="flex justify-end">{barEnd}</div>
            </>
          ) : (
            <>
              {upperTabs}
              {optionsMenu(upper)}
              {barEnd}
            </>
          )}
        </div>
      )}

      {body(tabs[0])}
      {body(tabs[1])}

      {split && !hidden && (
        <>
          <div
            key="divider"
            role="separator"
            aria-orientation="horizontal"
            aria-label={`Resize ${name} panes`}
            aria-valuemin={Math.round(SPLIT_MIN * 100)}
            aria-valuemax={Math.round(SPLIT_MAX * 100)}
            aria-valuenow={Math.round(shownSplit * 100)}
            tabIndex={0}
            className="focus-ring h-1 shrink-0 cursor-row-resize bg-border transition-colors hover:bg-primary/50 active:bg-primary"
            style={{ order: 2 }}
            onPointerDown={startDivider}
            onKeyDown={(e) => {
              const step = e.key === "ArrowUp" ? -0.05 : e.key === "ArrowDown" ? 0.05 : 0;
              if (step === 0) return;
              e.preventDefault();
              onAction({
                type: "set-split",
                split: Math.round((arrangement.split + step) * 100) / 100,
              });
            }}
          />
          <div
            key="bar-lower"
            className="flex shrink-0 items-center gap-1 border-y border-border bg-muted/40 px-1.5 py-1"
            style={{ order: 3 }}
          >
            <div
              role="tablist"
              aria-label={`Lower ${name} pane`}
              className="flex items-center gap-0.5 rounded-lg bg-muted p-0.5"
            >
              {tabButton(lower, false)}
            </div>
            {optionsMenu(lower)}
          </div>
        </>
      )}

      {drag && (
        <div aria-hidden className="pointer-events-none absolute inset-0 z-20" style={{ order: 9 }}>
          <div
            className={`absolute inset-x-1 top-0.5 h-8 rounded-md border-2 border-dashed ${zoneClass("upper-bar")}`}
          />
          <div
            className={`absolute inset-x-1 bottom-1 top-1/2 flex items-center justify-center rounded-md border-2 border-dashed text-xs text-muted-foreground ${zoneClass("lower-half")}`}
          >
            {split ? "Drop to swap" : "Drop to split"}
          </div>
        </div>
      )}
    </div>
  );
}
