import { type RefCallback, useCallback, useEffect, useRef, useState } from "react";

/**
 * Reports the real, browser-rendered height of the ref'd element, kept live via a
 * `ResizeObserver` — the DOM-measurement half of 005-resizable-canvas-boxes's "guarantee, not an
 * estimate" box-sizing fix (see `nodeLayout.ts`'s `computeMeasuredHeight`/`childYOffsets` and
 * research.md #2). No new dependency: `ResizeObserver` is a native browser API.
 *
 * Returns `null` until the very first measurement lands (a node's caller falls back to the
 * existing character-count estimate for that one frame, avoiding a 0-height flash). The height
 * is rounded *up* (`Math.ceil`) — rounding down could under-report by a fraction of a pixel and
 * risk clipping the very last sliver of text this feature exists to prevent.
 *
 * Uses a ref *callback* (not `useRef` + a separate `useEffect`) so the observer is attached and
 * torn down exactly when the element itself mounts/unmounts, including on remount.
 */
export function useMeasuredHeight<T extends HTMLElement>(): [RefCallback<T>, number | null] {
  const [height, setHeight] = useState<number | null>(null);
  const observerRef = useRef<ResizeObserver | null>(null);

  const ref = useCallback<RefCallback<T>>((el) => {
    observerRef.current?.disconnect();
    observerRef.current = null;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setHeight(Math.ceil(entry.contentRect.height));
    });
    observer.observe(el);
    observerRef.current = observer;
  }, []);

  // Belt-and-suspenders cleanup on unmount, in case the ref callback's own `el === null` teardown
  // (called by React on unmount) doesn't already run for some reason.
  useEffect(() => () => observerRef.current?.disconnect(), []);

  return [ref, height];
}
