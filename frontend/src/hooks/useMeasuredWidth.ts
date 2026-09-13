import { type RefCallback, useCallback, useLayoutEffect, useRef, useState } from "react";

/**
 * Reports the real, browser-rendered width of the ref'd element — the width counterpart to
 * `useMeasuredHeight.ts`, for the Pricing column's word-wrap toggle
 * (009-ui-fixes-next-iteration follow-up), which needs to know exactly how many pixels a
 * Price per Sku line's label has to work with before deciding where to cut it (`textWrap.ts`).
 *
 * Same dual-measurement-path design as `useMeasuredHeight.ts`, for the same reason: a
 * `ResizeObserver`-only version was found (005/007/008, this project's own history) to not
 * reliably fire for a backgrounded/unfocused tab. `useLayoutEffect` — part of React's
 * synchronous commit phase, not a browser API subject to that same throttling — runs
 * deterministically after every render as the primary path; `ResizeObserver` only covers the
 * one gap it can't (the element resizing without a React re-render, e.g. the column being
 * drag-resized by the user with no prop change on this particular element).
 *
 * Returns `null` until the very first measurement lands — callers should treat that as "not
 * measured yet" (`textWrap.ts`'s `splitForWrap` already treats a non-positive width that way).
 */
export function useMeasuredWidth<T extends HTMLElement>(): [RefCallback<T>, number | null] {
  const [width, setWidth] = useState<number | null>(null);
  const elRef = useRef<T | null>(null);
  const observerRef = useRef<ResizeObserver | null>(null);

  const setMeasuredWidth = useCallback((next: number) => {
    setWidth((prev) => (prev === next ? prev : next));
  }, []);

  const ref = useCallback<RefCallback<T>>(
    (el) => {
      observerRef.current?.disconnect();
      observerRef.current = null;
      elRef.current = el;
      if (!el) return;
      const observer = new ResizeObserver((entries) => {
        const entry = entries[0];
        if (entry) setMeasuredWidth(entry.contentRect.width);
      });
      observer.observe(el);
      observerRef.current = observer;
    },
    [setMeasuredWidth],
  );

  // Runs after every render (deliberately no dependency array) — the primary measurement
  // path; see the module comment above for why this, not `ResizeObserver` alone.
  useLayoutEffect(() => {
    if (elRef.current) {
      setMeasuredWidth(elRef.current.getBoundingClientRect().width);
    }
  });

  // Belt-and-suspenders cleanup on unmount, in case the ref callback's own `el === null`
  // teardown (called by React on unmount) doesn't already run for some reason.
  useLayoutEffect(() => () => observerRef.current?.disconnect(), []);

  return [ref, width];
}
