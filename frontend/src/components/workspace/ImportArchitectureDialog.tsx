import { useState } from "react";

import type { ImportableArchitectures } from "../../api/client";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";
import { Input } from "../ui/input";

type Picked = { id: string; name: string };

/**
 * The "Import" list (012-user-accounts-sharing, spec FR-023-028): every other user's public
 * architectures, grouped by owner (Admin group first, then alphabetical — pre-sorted
 * server-side, `GET /architectures/importable`), then a naming prompt pre-filled
 * `"My {original name}"`. Two steps in one `Dialog` (research.md §9's `Dialog`-reuse
 * precedent), rather than two separate dialogs, since only one is ever shown at a time.
 */
export function ImportArchitectureDialog({
  open,
  onOpenChange,
  data,
  onConfirm,
  isSubmitting,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  data: ImportableArchitectures | undefined;
  onConfirm: (architectureId: string, name: string) => void;
  isSubmitting: boolean;
}) {
  const [picked, setPicked] = useState<Picked | null>(null);
  const [name, setName] = useState("");

  function handleOpenChange(next: boolean) {
    onOpenChange(next);
    if (!next) setPicked(null);
  }

  function handlePick(architecture: Picked) {
    setPicked(architecture);
    setName(`My ${architecture.name}`);
  }

  function handleConfirm() {
    if (!picked || !name.trim()) return;
    onConfirm(picked.id, name.trim());
  }

  const groups = data?.groups ?? [];

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{picked ? "Name your copy" : "Import an architecture"}</DialogTitle>
        </DialogHeader>

        {!picked && (
          <div className="flex max-h-80 flex-col gap-3 overflow-y-auto">
            {groups.length === 0 && (
              <p className="text-2xs text-muted-foreground">
                No other user has shared a public architecture yet.
              </p>
            )}
            {groups.map((group) => (
              <div key={group.owner_username} className="flex flex-col gap-1">
                <h3 className="text-2xs font-medium text-muted-foreground">
                  {group.owner_username}
                </h3>
                <ul className="flex flex-col gap-0.5">
                  {group.architectures.map((architecture) => (
                    <li key={architecture.id}>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="w-full justify-start"
                        onClick={() => handlePick(architecture)}
                      >
                        {architecture.name}
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

        {picked && (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              handleConfirm();
            }}
          >
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-label="Copy name"
              autoFocus
            />
            <DialogFooter>
              <Button type="submit" disabled={!name.trim() || isSubmitting}>
                Import
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
