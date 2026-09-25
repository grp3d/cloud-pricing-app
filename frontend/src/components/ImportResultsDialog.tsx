import { Check, X } from "lucide-react";

import type { ImportResult } from "../api/client";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";

/**
 * Post-import status popup for the Admin tab's "Import Architectures from Disk"
 * (014-architecture-templates-import-export, spec FR-019, FR-022): one row per architecture in
 * the file — a green check or red X, its name, and a brief failure reason — or, when the file
 * as a whole was rejected, just that message.
 */
export function ImportResultsDialog({
  open,
  onOpenChange,
  results,
  failedMessage,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  results: ImportResult[];
  failedMessage?: string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Import results</DialogTitle>
        </DialogHeader>
        {failedMessage ? (
          <p className="text-2xs text-destructive">{failedMessage}</p>
        ) : results.length === 0 ? (
          <p className="text-2xs text-muted-foreground">No architectures were found in this file.</p>
        ) : (
          <table className="w-full border-collapse text-2xs">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="py-1.5 pr-2">Status</th>
                <th className="py-1.5 pr-2">Architecture</th>
                <th className="py-1.5">Error</th>
              </tr>
            </thead>
            <tbody>
              {results.map((result, index) => (
                <tr key={index} className="border-b border-border align-top">
                  <td className="py-1.5 pr-2">
                    {result.status === "success" ? (
                      <Check className="size-4 text-green-600" aria-label="Imported" />
                    ) : (
                      <X className="size-4 text-destructive" aria-label="Failed" />
                    )}
                  </td>
                  <td className="py-1.5 pr-2">{result.name ?? `(unnamed #${index + 1})`}</td>
                  <td className="py-1.5">{result.status === "failed" ? result.error : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </DialogContent>
    </Dialog>
  );
}
