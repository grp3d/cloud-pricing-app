import { useLayoutEffect, useRef } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";

/** Font sizes tried in turn, largest first: 12px matches the tab labels beside it. */
const SIZES_PX = [12, 11, 10];

/**
 * 023: a one-line title, centred, that shrinks to fit the space it has, down to 10px, and is cut
 * off with an ellipsis after that. The full text is its tooltip and its accessible name.
 */
export function FitTitle({ text }: { text: string }) {
  const ref = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const fit = () => {
      // Try each size until the text fits; the last one is cut off if it still doesn't.
      for (const px of SIZES_PX) {
        element.style.fontSize = `${px}px`;
        if (element.scrollWidth <= element.clientWidth) return;
      }
    };
    fit();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(fit);
    observer.observe(element);
    return () => observer.disconnect();
  }, [text]);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <h2 className="min-w-0 px-1 text-center font-normal text-foreground">
          <span ref={ref} tabIndex={0} aria-label={text} className="block truncate rounded-sm">
            {text}
          </span>
        </h2>
      </TooltipTrigger>
      <TooltipContent>{text}</TooltipContent>
    </Tooltip>
  );
}
