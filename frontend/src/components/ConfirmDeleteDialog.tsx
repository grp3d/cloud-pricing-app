import { Trash2 } from "lucide-react";

import { Button } from "./ui/button";

interface Props {
  itemLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/** A blocking confirm-before-delete prompt, per FR-014/FR-015 ("system MUST prompt for
 * confirmation before deleting"). Deliberately a plain modal — no dialog library needed for
 * one yes/no prompt (Constitution Principle VI). */
export function ConfirmDeleteDialog({ itemLabel, onConfirm, onCancel }: Props) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 flex items-center justify-center bg-black/40"
    >
      <div className="min-w-70 rounded-lg border border-border bg-card p-6 shadow-lg">
        <p className="text-sm">
          Delete <strong>{itemLabel}</strong>? This can&apos;t be undone from the UI.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" variant="destructive" size="sm" onClick={onConfirm} autoFocus>
            <Trash2 /> Delete
          </Button>
        </div>
      </div>
    </div>
  );
}
