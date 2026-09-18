import { createContext, useContext, useState, type ReactNode } from "react";

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../ui/dialog";

const PermissionDeniedContext = createContext<() => void>(() => {});

/**
 * Shared "Insufficient Permissions" popup (012-user-accounts-sharing follow-up): rendered once
 * at the app root so `RequireAdmin` can surface it on top of wherever the caller gets bounced
 * back to, rather than owning its own dialog instance per guarded route.
 */
export function PermissionDeniedProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <PermissionDeniedContext.Provider value={() => setOpen(true)}>
      {children}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Insufficient Permissions</DialogTitle>
          </DialogHeader>
          <p className="text-2xs text-muted-foreground">
            You don&apos;t have permission to view that page.
          </p>
        </DialogContent>
      </Dialog>
    </PermissionDeniedContext.Provider>
  );
}

export function usePermissionDenied() {
  return useContext(PermissionDeniedContext);
}
