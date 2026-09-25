import { type RefCallback, useCallback, useLayoutEffect, useRef, useState } from "react";

/**
 * Reports the real, browser-rendered height of the ref'd element — the DOM-measurement half
 * of 005-resizable-canvas-boxes's "guarantee, not an estimate" box-sizing fix (see
 * `nodeLayout.ts`'s `computeMeasuredHeight`/`childYOffsets` and research.md #2).
 *
 * Two measurement paths, deliberately redundant (008-ui-updates-corrections, FR-002;
 * research.md §1b): a `useLayoutEffect` that runs after *every* render and reads the
 * element's real height synchronously via `getBoundingClientRect()`, plus a `ResizeObserver`
 * as a supplementary path for the one case the layout effect can't catch — the element's own
 * size changing *without* a React re-render (e.g. a web font finishing an async load and
 * reflowing text after the initial paint, with no prop change to re-trigger the component).
 *
 * The layout-effect path was added after 005/007 investigations conclusively found the
 * `ResizeObserver`-only version's callback would not reliably fire — confirmed, via temporary
 * instrumentation, to correlate with the automation tab never being OS-focused
 * (`document.hidden === true`), a known Chrome behavior that throttles `ResizeObserver`
 * delivery for backgrounded tabs — but the user separately confirmed this box-sizing
 * behavior *still* doesn't reliably work in their own, presumably-focused, real browser, so
 * that explanation alone was not sufficient (`005-box-autoresize-not-observed` project
 * memory). `useLayoutEffect` is part of React's own synchronous commit phase, not a browser
 * API subject to the same background-tab scheduling — it runs deterministically after every
 * render regardless of tab focus, so relying on it as the primary path (with `ResizeObserver`
 * only for the one gap it can't cover) removes the async-delivery dependency this bug has
 * been traced to twice now, without needing to find one single root cause to justify the
 * change (Constitution Principle VI: a more reliable measurement primitive, not a rewrite).
 *
 * Returns `null` until the very first measurement lands (a node's caller falls back to the
 * existing character-count estimate for that one frame, avoiding a 0-height flash). The height
 * is rounded *up* (`Math.ceil`) — rounding down could under-report by a fraction of a pixel and
 * risk clipping the very last sliver of text this feature exists to prevent.
 *
 * Uses a ref *callback* (not `useRef` + a separate `useEffect`) so the observer/measurement is
 * attached and torn down exactly when the element itself mounts/unmounts, including on remount.
 */
export function useMeasuredHeight<T extends HTMLElement>(): [RefCallback<T>, number | null] {
  const [height, setHeight] = useState<number | null>(null);
  const elRef = useRef<T | null>(null);
  const observerRef = useRef<ResizeObserver | null>(null);

  const setMeasuredHeight = useCallback((next: number) => {
    setHeight((prev) => (prev === next ? prev : next));
  }, []);

  const ref = useCallback<RefCallback<T>>(
    (el) => {
      observerRef.current?.disconnect();
      observerRef.current = null;
      elRef.current = el;
      if (!el) return;
      const observer = new ResizeObserver((entries) => {
        const entry = entries[0];
        if (entry) setMeasuredHeight(Math.ceil(entry.contentRect.height));
      });
      observer.observe(el);
      observerRef.current = observer;
    },
    [setMeasuredHeight],
  );

  // Runs after every render (deliberately no dependency array) — the primary measurement
  // path; see the module comment above for why this, not `ResizeObserver` alone, is now the
  // one this hook leans on. 015-canvas-service-icons: reads `offsetHeight` (layout size), not
  // `getBoundingClientRect()` — the measured element lives inside React Flow's zoomed viewport,
  // and a bounding rect includes that CSS transform, so at the default 0.7 zoom it under-reported
  // (clipping a box's last row) and when zoomed in it over-reported, while the `ResizeObserver`
  // path above (untransformed `contentRect`) reported the true size. Both paths now agree, in
  // the node's own coordinate space, which is what the box's height is set in.
  useLayoutEffect(() => {
    if (elRef.current) {
      setMeasuredHeight(Math.ceil(elRef.current.offsetHeight));
    }
  });

  // Belt-and-suspenders cleanup on unmount, in case the ref callback's own `el === null`
  // teardown (called by React on unmount) doesn't already run for some reason.
  useLayoutEffect(() => () => observerRef.current?.disconnect(), []);

  return [ref, height];
}
