import { useState } from "react";

import type { Region } from "../../api/client";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";

/**
 * Region-selection prompt shown when creating a new VPC or unattached Application collection
 * (010-multi-region-support, spec FR-001, FR-017) — reuses the `Dialog` primitive 009's "Add
 * Connector" feature already introduced (research.md §7), rather than a new modal pattern.
 * Controlled from the caller: `WorkspacePage` decides when to open it (skipped entirely when
 * creating an Application inside an already-selected VPC, per FR-001a).
 */
export function RegionSelectDialog({
  open,
  onOpenChange,
  regions,
  onConfirm,
  isSubmitting,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  regions: Region[];
  onConfirm: (region: string) => void;
  isSubmitting: boolean;
}) {
  const [region, setRegion] = useState<string | undefined>(undefined);

  function handleOpenChange(next: boolean) {
    onOpenChange(next);
    if (!next) setRegion(undefined);
  }

  function handleConfirm() {
    if (!region) return;
    onConfirm(region);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Choose a region</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium" htmlFor="region-select">
            AWS Region
          </label>
          <Select value={region} onValueChange={setRegion}>
            <SelectTrigger id="region-select" className="w-full">
              <SelectValue placeholder="Select a region" />
            </SelectTrigger>
            <SelectContent>
              {regions.map((r) => (
                <SelectItem key={r.code} value={r.code}>
                  {r.code}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <Button type="button" onClick={handleConfirm} disabled={!region || isSubmitting}>
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
