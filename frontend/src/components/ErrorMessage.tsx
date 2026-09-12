import { AlertTriangle } from "lucide-react";

import { Button } from "./ui/button";

interface Props {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}

/**
 * A visible, distinct failure state — never silence, never conflated with an empty/"no
 * results" outcome (FR-018 / Edge Cases). Used for query/mutation errors that TanStack Query
 * does not surface to React's render tree by default (it swallows async errors unless
 * `throwOnError` is set, so `ErrorBoundary` alone cannot catch these — see
 * `frontend/src/components/ErrorBoundary.tsx` for the render-phase equivalent).
 */
export function ErrorMessage({ message, onRetry, retryLabel = "Retry" }: Props) {
  return (
    <p role="alert" className="flex items-center gap-1.5 text-xs text-destructive">
      <AlertTriangle className="size-4 shrink-0" /> {message}
      {onRetry && (
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          {retryLabel}
        </Button>
      )}
    </p>
  );
}
