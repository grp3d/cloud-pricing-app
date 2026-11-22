/**
 * 025 (FR-017, contracts/proposal-ui.md "Unsaved-work dialog"): before the agent opens another
 * architecture while the open one has unsaved input, the user chooses Save and continue or
 * Discard and continue. Nothing opens until they choose; Escape and clicking outside do
 * nothing. If saving fails, the dialog says so and stays.
 *
 * 027 (FR-011): Log out asks the same, with its own description and a Cancel that keeps the
 * user logged in.
 */
import { useState } from "react";

import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";

export function UnsavedWorkDialog({
  open,
  currentName,
  nextName,
  onSave,
  onDiscard,
  description,
  onCancel,
}: {
  open: boolean;
  currentName: string;
  /** What the agent is opening; unused when `description` is given. */
  nextName?: string;
  /** Replaces "The agent is opening …" (027: "You're logging out."). */
  description?: string;
  /** Shows a Cancel button (027: Log out). */
  onCancel?: () => void;
  /** Saves; resolves to false when that failed. */
  onSave: () => Promise<boolean>;
  onDiscard: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  async function save() {
    setSaving(true);
    setFailed(false);
    const ok = await onSave().catch(() => false);
    setSaving(false);
    if (!ok) setFailed(true);
  }

  return (
    <Dialog open={open}>
      <DialogContent
        showCloseButton={false}
        onEscapeKeyDown={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Unsaved changes in &apos;{currentName}&apos;</DialogTitle>
          <DialogDescription>
            {description ?? <>The agent is opening &apos;{nextName}&apos;.</>}
          </DialogDescription>
        </DialogHeader>
        {failed && (
          <p role="alert" className="text-sm text-destructive">
            Your changes couldn&apos;t be saved. The Service tab says why. Fix them, or discard
            them.
          </p>
        )}
        <DialogFooter>
          {onCancel && (
            <Button type="button" variant="ghost" disabled={saving} onClick={onCancel}>
              Cancel
            </Button>
          )}
          <Button type="button" variant="outline" disabled={saving} onClick={onDiscard}>
            Discard and continue
          </Button>
          <Button type="button" disabled={saving} onClick={() => void save()}>
            Save and continue
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
