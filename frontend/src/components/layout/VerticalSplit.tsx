/**
 * 024 (FR-018, contracts/results-pane-ui.md "Layout"): two panes side by side with a vertical
 * divider the user drags (or moves with the arrow keys, 5% a step; Home and End go to the
 * limits). Below `stackBelow` pixels of width the second pane goes under the first, with no
 * divider, so a narrow Agent tab stays readable. Without `second`, the first fills the space.
 */
import { type ReactNode, useEffect, useRef, useState } from "react";

export const STACK_BELOW_PX = 700;

export type VerticalSplitProps = {
  first: ReactNode;
  second: ReactNode | null;
  /** The first pane's share of the width. */
  split: number;
  min: number;
  max: number;
  /** Called once a drag or key press ends, with the new share. */
  onCommit: (split: number) => void;
  label: string;
  stackBelow?: number;
};

export function VerticalSplit({
  first,
  second,
  split,
  min,
  max,
  onCommit,
  label,
  stackBelow = STACK_BELOW_PX,
}: VerticalSplitProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState<number | null>(null);
  const [live, setLive] = useState<number | null>(null);
  const clamp = (value: number) => Math.min(max, Math.max(min, value));
  const shown = clamp(live ?? split);

  useEffect(() => {
    const element = containerRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      setWidth(entries[0]?.contentRect.width ?? element.clientWidth);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const stacked = width !== null && width < stackBelow;

  function startDrag(e: React.PointerEvent<HTMLDivElement>) {
    e.preventDefault();
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0) return;
    const target = e.currentTarget;
    target.setPointerCapture?.(e.pointerId);
    let latest = shown;
    const onMove = (ev: PointerEvent) => {
      latest = clamp((ev.clientX - rect.left) / rect.width);
      setLive(latest);
    };
    const onUp = () => {
      target.removeEventListener("pointermove", onMove);
      target.removeEventListener("pointerup", onUp);
      setLive(null);
      onCommit(Math.round(latest * 100) / 100);
    };
    target.addEventListener("pointermove", onMove);
    target.addEventListener("pointerup", onUp);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    let next: number | null = null;
    if (e.key === "ArrowLeft") next = shown - 0.05;
    else if (e.key === "ArrowRight") next = shown + 0.05;
    else if (e.key === "Home") next = min;
    else if (e.key === "End") next = max;
    if (next === null) return;
    e.preventDefault();
    onCommit(Math.round(clamp(next) * 100) / 100);
  }

  // One tree whatever the layout, so the first pane (the conversation, maybe mid-answer) is
  // never remounted when the second appears, or when the width crosses `stackBelow`.
  const sideBySide = second !== null && !stacked;
  return (
    <div
      ref={containerRef}
      className={`flex h-full min-h-0 min-w-0 ${sideBySide ? "flex-row" : "flex-col"}`}
    >
      <div
        key="first"
        className="flex min-h-0 min-w-0 flex-col"
        style={sideBySide ? { flex: `0 0 ${shown * 100}%` } : { flex: "1 1 0%" }}
      >
        {first}
      </div>
      {sideBySide && (
        <div
          key="divider"
          role="separator"
          aria-orientation="vertical"
          aria-label={label}
          aria-valuemin={Math.round(min * 100)}
          aria-valuemax={Math.round(max * 100)}
          aria-valuenow={Math.round(shown * 100)}
          tabIndex={0}
          className="focus-ring w-1 shrink-0 cursor-col-resize bg-border transition-colors hover:bg-primary/50 active:bg-primary"
          onPointerDown={startDrag}
          onKeyDown={onKeyDown}
        />
      )}
      {second !== null && (
        <div
          key="second"
          className={
            sideBySide
              ? "flex min-h-0 min-w-0 flex-1 flex-col"
              : "flex min-h-[240px] min-w-0 shrink-0 basis-1/2 flex-col border-t border-border"
          }
        >
          {second}
        </div>
      )}
    </div>
  );
}
