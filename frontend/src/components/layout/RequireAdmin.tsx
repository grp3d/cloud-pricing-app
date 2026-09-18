import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api/client";
import { usePermissionDenied } from "./PermissionDeniedDialog";

const LAST_NON_ADMIN_PATH_KEY = "cloud-pricing-last-non-admin-path";

/**
 * Route guard for `/admin` (012-user-accounts-sharing follow-up): a non-admin identity — either
 * because they typed the URL directly, or because an admin's session changed to a non-admin
 * user while `/admin` was already open — never sees `AdminPage` render at all. It's bounced
 * back to wherever it was before (tracked in `sessionStorage` by `useTrackLastNonAdminPath`, so
 * this survives a hard URL-bar navigation, not just client-side routing) and shown the shared
 * "Insufficient Permissions" popup on top of that page.
 */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const currentUser = useQuery({ queryKey: ["currentUser"], queryFn: api.getCurrentUser });
  const navigate = useNavigate();
  const openPermissionDenied = usePermissionDenied();
  const hasRedirected = useRef(false);

  const isKnownNonAdmin = currentUser.data !== undefined && !currentUser.data.is_admin;

  useEffect(() => {
    if (isKnownNonAdmin && !hasRedirected.current) {
      hasRedirected.current = true;
      const lastPath = sessionStorage.getItem(LAST_NON_ADMIN_PATH_KEY) ?? "/";
      navigate(lastPath, { replace: true });
      openPermissionDenied();
    }
  }, [isKnownNonAdmin, navigate, openPermissionDenied]);

  if (currentUser.data?.is_admin) return <>{children}</>;
  return null;
}

/** Records every route visited that isn't `/admin`, so `RequireAdmin` can send a rejected
 * visitor back to it even after a full page load (typing `/admin` in the URL bar). */
export function useTrackLastNonAdminPath(pathname: string) {
  useEffect(() => {
    if (pathname !== "/admin") {
      sessionStorage.setItem(LAST_NON_ADMIN_PATH_KEY, pathname);
    }
  }, [pathname]);
}
