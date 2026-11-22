import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { NavLink, useMatch } from "react-router-dom";

import { api } from "../../api/client";
import { cn } from "cn";
import { useArchitectureLibrary } from "../../hooks/useArchitectureLibrary";
import { ConfirmDeleteDialog } from "../ConfirmDeleteDialog";
import { ImportArchitectureDialog } from "../workspace/ImportArchitectureDialog";
import { ArchitectureMenu, NAME_FIELD_ATTR } from "./ArchitectureMenu";
import { HeaderMenu } from "./HeaderMenu";
import { HEADER_CONTROL, HEADER_CURRENT } from "./headerStyles";
import { UserMenu } from "./UserMenu";

/**
 * Top-level tab bar (012-user-accounts-sharing, spec FR-001-003): "Cloud Pricing" (the
 * workspace), "Trends" (019) and "Admin" (admins only, from `GET /auth/me`), plus the person
 * icon (FR-014), on every page.
 *
 * 021 (US1, FR-001, FR-005, FR-007a): "Cloud Pricing" is a split control. The label still goes
 * to the workspace; the chevron beside it opens the architecture menu, which replaces the
 * workspace's old Column 1 and works from every page.
 *
 * 021 US5 (FR-035, FR-036): a dark zinc band with 14px navigation text, 48px tall. The open
 * architecture's name is shown above the canvas (`WorkspacePage`), not here.
 */

export function TopTabs() {
  const currentUser = useQuery({ queryKey: ["currentUser"], queryFn: api.getCurrentUser });
  const isAdmin = currentUser.data?.is_admin ?? false;

  const [menuOpen, setMenuOpen] = useState(false);
  const library = useArchitectureLibrary({ onNavigated: () => setMenuOpen(false) });
  // Opening a dialog from the menu closes the menu first; the dialogs live outside it.
  const menuLibrary = {
    ...library,
    requestDelete: (arch: Parameters<typeof library.requestDelete>[0]) => {
      setMenuOpen(false);
      library.requestDelete(arch);
    },
    openImport: (provider: string) => {
      setMenuOpen(false);
      library.openImport(provider);
    },
  };

  // "Cloud Pricing" is the current page on the workspace, with or without an open architecture.
  const onArchitecture = Boolean(useMatch("/architectures/:architectureId"));

  return (
    <header
      data-app-header
      className="flex h-12 shrink-0 items-center gap-2 border-b border-header-border bg-header px-3 text-header-foreground"
    >
      <UserMenu />
      <nav className="flex min-w-0 items-center gap-1">
        <div className="flex items-center">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              cn(HEADER_CONTROL, "rounded-r-none", (isActive || onArchitecture) && HEADER_CURRENT)
            }
          >
            Cloud Pricing
          </NavLink>
          {/* 027 (FR-002): the same menu behaviour as the user menu. */}
          <HeaderMenu
            open={menuOpen}
            onOpenChange={setMenuOpen}
            trigger={<ChevronDown className="size-4" />}
            triggerLabel="Open architecture menu"
            triggerClassName="rounded-l-none px-1.5"
            contentLabel="Architectures"
            contentClassName="max-h-[min(36rem,calc(100vh-4rem))] w-auto overflow-y-auto"
            onEscapeKeyDown={(e) => {
              // The first Escape in a name field clears the name; only the next one closes.
              const active = document.activeElement;
              if (active instanceof HTMLElement && active.hasAttribute(NAME_FIELD_ATTR)) {
                e.preventDefault();
              }
            }}
          >
            <ArchitectureMenu library={menuLibrary} />
          </HeaderMenu>
        </div>
        {/* 019 (FR-010): the Trends page. */}
        <NavLink
          to="/trends"
          className={({ isActive }) => cn(HEADER_CONTROL, isActive && HEADER_CURRENT)}
        >
          Trends
        </NavLink>
        {isAdmin && (
          <NavLink
            to="/admin"
            className={({ isActive }) => cn(HEADER_CONTROL, isActive && HEADER_CURRENT)}
          >
            Admin
          </NavLink>
        )}
      </nav>

      {/* Outside the popover, so they stay open when it closes. */}
      {library.pendingDelete && (
        <ConfirmDeleteDialog
          itemLabel={library.pendingDelete.name}
          onCancel={library.cancelDelete}
          onConfirm={library.confirmDelete}
        />
      )}
      <ImportArchitectureDialog
        open={library.importProvider !== null}
        onOpenChange={(open) => !open && library.closeImport()}
        provider={library.importProvider ?? "aws"}
        data={library.importable}
        onConfirm={library.importArchitecture}
        isSubmitting={library.isImporting}
      />
    </header>
  );
}
