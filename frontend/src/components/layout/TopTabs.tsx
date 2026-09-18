import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";

import { api } from "../../api/client";
import { Button } from "../ui/button";
import { IdentityMenu } from "./IdentityMenu";

/**
 * Top-level tab bar (012-user-accounts-sharing, spec FR-001-003): "Cloud Pricing" (the
 * existing workspace, active by default), "Trends" (visibly present but permanently disabled
 * — out of scope this feature), and "Admin" (shown only for the current identity's admin
 * status, from `GET /auth/me`). The person icon (FR-014) lives here too, since it must stay
 * visible regardless of which tab is active — a new top-level shell above `WorkspacePage`,
 * which previously had no chrome of its own (research.md §8).
 */
export function TopTabs() {
  const currentUser = useQuery({ queryKey: ["currentUser"], queryFn: api.getCurrentUser });
  const isAdmin = currentUser.data?.is_admin ?? false;

  return (
    <header className="flex h-10 shrink-0 items-center gap-2 border-b border-border px-2">
      <IdentityMenu />
      <nav className="flex items-center gap-1">
        <NavLink to="/" end>
          {({ isActive }) => (
            <Button asChild variant={isActive ? "secondary" : "ghost"} size="sm">
              <span>Cloud Pricing</span>
            </Button>
          )}
        </NavLink>
        <Button variant="ghost" size="sm" disabled aria-label="Trends (coming soon)">
          Trends
        </Button>
        {isAdmin && (
          <NavLink to="/admin">
            {({ isActive }) => (
              <Button asChild variant={isActive ? "secondary" : "ghost"} size="sm">
                <span>Admin</span>
              </Button>
            )}
          </NavLink>
        )}
      </nav>
    </header>
  );
}
