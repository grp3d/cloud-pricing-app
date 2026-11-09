import {
  Calculator,
  MoreHorizontal,
  PanelRightClose,
  PanelRightOpen,
  SlidersHorizontal,
} from "lucide-react";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";

import {
  type InspectorAction,
  type InspectorArrangement,
  type InspectorTab,
  SPLIT_MAX,
  SPLIT_MIN,
  other,
} from "../../lib/inspectorLayout";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

const TAB_LABELS: Record<InspectorTab, string> = { pricing: "Pricing", service: "Service" };
const TAB_ORDER: InspectorTab[] = ["pricing", "service"];
/** A drag starts only after this much pointer movement, so a click still selects the tab. */
const DRAG_THRESHOLD_PX = 4;

type DropZone = "upper-bar" | "lower-half" | null;

export interface InspectorPanelProps {
  arrangement: InspectorArrangement;
  onAction: (action: InspectorAction) => void;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  /** A calculation finished while collapsed (FR-018a): the rail's Pricing button is marked. */
  newResult: boolean;
  width: number;
  pricing: ReactNode;
  service: ReactNode;
}

/**
 * The workspace's right-hand inspector (021, US2 and US3): the Price Summary and the Service
 * Editor as two tabs, Pricing and Service.
 *
 * - **Merged:** one pane, one visible tab (FR-014).
 * - **Split:** an upper and a lower pane, one tab each, with a draggable divider (FR-019 to
 *   FR-021). Tabs are dragged with pointer events to the lower half (split or swap) or onto
 *   the upper tab bar (merge); each pane's tab options menu does the same from the keyboard
 *   (FR-022). Escape or a drop elsewhere cancels (FR-023).
 * - **Collapsed:** a narrow rail with a button per tab (FR-018a).
 *
 * Both tab bodies stay mounted in one parent in every arrangement (shown or hidden, and
 * placed with CSS `order`), so unsaved Service input and the Pricing tab's word-wrap choice
 * survive tab switches, splits, merges and swaps (FR-017). The tabs are therefore written
 * with the ARIA tab roles directly rather than with a Tabs component, which would re-parent
 * the bodies on every split or merge. Every arrangement change goes through `onAction`, which
 * `WorkspacePage` feeds to `nextArrangement` (`inspectorLayout.ts`).
 */
export function InspectorPanel({
  arrangement,
  onAction,
  collapsed,
  onCollapsedChange,
  newResult,
  width,
  pricing,
  service,
}: InspectorPanelProps) {
  const idBase = useId();
  const tabId = (t: InspectorTab) => `${idBase}-tab-${t}`;
  const panelId = (t: InspectorTab) => `${idBase}-panel-${t}`;
  const split = arrangement.mode === "split";
  const upper = split ? arrangement.upper : arrangement.front;
  const lower = other(arrangement.upper);

  const containerRef = useRef<HTMLDivElement>(null);
  const upperBarRef = useRef<HTMLDivElement>(null);

  // --- Divider (FR-021): live while dragging, saved on release. ---
  const [liveSplit, setLiveSplit] = useState<number | null>(null);
  const shownSplit = liveSplit ?? arrangement.split;

  // --- Tab drag (FR-019, FR-020, FR-023). ---
  const [drag, setDrag] = useState<{ tab: InspectorTab; zone: DropZone } | null>(null);
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

  function startTabPointer(tab: InspectorTab, e: React.PointerEvent<HTMLButtonElement>) {
    if (e.button !== 0) return;
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

  function tabButton(tab: InspectorTab, inMergedBar: boolean) {
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
        className={`focus-ring relative h-7 cursor-grab rounded-md px-2.5 text-xs font-medium transition-colors active:cursor-grabbing ${
          selected
            ? "bg-background text-foreground shadow-xs"
            : "text-muted-foreground hover:bg-accent hover:text-foreground"
        } ${drag?.tab === tab ? "opacity-60" : ""}`}
        onClick={() => onAction({ type: "select-tab", tab })}
        onKeyDown={(e) => {
          if (!inMergedBar) return;
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
        {TAB_LABELS[tab]}
      </button>
    );
  }

  function optionsMenu(tab: InspectorTab) {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-xs" aria-label={`${TAB_LABELS[tab]} tab options`}>
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

  function collapseButton() {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Collapse inspector"
            className="ml-auto"
            onClick={() => onCollapsedChange(true)}
          >
            <PanelRightClose />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Collapse</TooltipContent>
      </Tooltip>
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
  function body(tab: InspectorTab) {
    const visible = !collapsed && (split || arrangement.front === tab);
    const isUpper = tab === upper;
    const style: React.CSSProperties = split
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
        hidden={!visible}
        // FR-032: pane heights ease over 150ms on split, merge, swap and keyboard resizes;
        // not while the divider is being dragged, where they follow the pointer.
        className={`flex min-h-0 flex-col overflow-hidden ${
          split && liveSplit === null ? "transition-[flex-grow] duration-150 ease-out" : ""
        }`}
        style={style}
      >
        {tab === "pricing" ? pricing : service}
      </div>
    );
  }

  const rail = (
    <div className="flex flex-col items-center gap-2 py-2">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Expand inspector"
            onClick={() => onCollapsedChange(false)}
          >
            <PanelRightOpen />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="left">Expand</TooltipContent>
      </Tooltip>
      {TAB_ORDER.map((tab) => {
        const marked = tab === "pricing" && newResult;
        return (
          <Tooltip key={tab}>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={marked ? "Pricing — new result" : TAB_LABELS[tab]}
                className="relative"
                onClick={() => {
                  onAction({ type: "select-tab", tab });
                  onCollapsedChange(false);
                }}
              >
                {tab === "pricing" ? <Calculator /> : <SlidersHorizontal />}
                {marked && (
                  <span
                    aria-hidden
                    className="absolute top-1 right-1 size-2 rounded-full bg-primary"
                  />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent side="left">
              {marked ? "Pricing: a new result is waiting" : TAB_LABELS[tab]}
            </TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );

  const zoneClass = (zone: Exclude<DropZone, null>) =>
    drag?.zone === zone ? "border-primary bg-primary/10" : "border-border bg-muted/40";

  return (
    <aside
      aria-label="Inspector"
      className="flex h-full shrink-0 flex-col border-l border-border bg-background"
      style={{ width: collapsed ? 56 : width }}
    >
      {collapsed && rail}
      {/* Always rendered, hidden while collapsed, so the bodies are never remounted. */}
      <div
        ref={containerRef}
        hidden={collapsed}
        className="relative flex min-h-0 flex-1 flex-col overflow-y-auto"
      >
        {!collapsed && (
          <div
            key="bar-upper"
            ref={upperBarRef}
            className="flex shrink-0 items-center gap-1 border-b border-border bg-muted/40 px-1.5 py-1"
            style={{ order: 0 }}
          >
            <div
              role="tablist"
              aria-label={split ? "Upper inspector pane" : "Inspector tabs"}
              className="flex items-center gap-0.5 rounded-lg bg-muted p-0.5"
            >
              {split ? tabButton(upper, false) : TAB_ORDER.map((t) => tabButton(t, true))}
            </div>
            {optionsMenu(upper)}
            {collapseButton()}
          </div>
        )}

        {body("pricing")}
        {body("service")}

        {split && !collapsed && (
          <>
            <div
              key="divider"
              role="separator"
              aria-orientation="horizontal"
              aria-label="Resize inspector panes"
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
                aria-label="Lower inspector pane"
                className="flex items-center gap-0.5 rounded-lg bg-muted p-0.5"
              >
                {tabButton(lower, false)}
              </div>
              {optionsMenu(lower)}
            </div>
          </>
        )}

        {drag && (
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 z-20"
            style={{ order: 9 }}
          >
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
    </aside>
  );
}
