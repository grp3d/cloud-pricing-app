import { useQuery, useQueryClient } from "@tanstack/react-query";
import { User } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useMatch, useNavigate } from "react-router-dom";

import { type ArchitectureDetail, api } from "../../api/client";
import { onIdentityChanged } from "../../lib/identity";
import { resetTheme, useTheme } from "../../lib/theme";
import { unsavedWork } from "../../lib/unsavedWork";
import { LoginDialog } from "../auth/LoginDialog";
import { UnsavedWorkDialog } from "../workspace/UnsavedWorkDialog";
import { HeaderMenu, MENU_ITEM_ATTR } from "./HeaderMenu";

/**
 * 027 (FR-001 to FR-011, contracts/user-menu-ui.md): the person icon's menu, on the same
 * `HeaderMenu` as the Cloud Pricing menu. In order: the username or Guest (a label), Log in or
 * Log out, and Settings with Colour theme. There is no Change user: log out, then log in.
 * Replaces 012's IdentityMenu.
 */
export function UserMenu() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [loginOpen, setLoginOpen] = useState(false);
  const [confirmLogOut, setConfirmLogOut] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [theme, setTheme] = useTheme();
  const openId = useMatch("/architectures/:architectureId")?.params.architectureId;

  const currentUser = useQuery({ queryKey: ["currentUser"], queryFn: api.getCurrentUser });
  const username = currentUser.data?.username ?? null;
  const name = username ?? "Guest";

  function changedIdentity() {
    // A new identity's own data (architectures, admin status, settings) is entirely different
    // from the previous identity's: reset every query and reload the preferences.
    onIdentityChanged(queryClient);
    // A logged-in Admin on the Admin tab who becomes someone else must not stay there.
    navigate("/");
  }

  function openLogin() {
    setMenuOpen(false);
    setLoginOpen(true);
  }

  function requestLogOut() {
    setMenuOpen(false);
    if (unsavedWork.dirty) setConfirmLogOut(true);
    else logOut();
  }

  function logOut() {
    setConfirmLogOut(false);
    api.logOut();
    resetTheme();
    changedIdentity();
  }

  const openName =
    (openId && queryClient.getQueryData<ArchitectureDetail>(["architecture", openId])?.name) ||
    "this architecture";
  const otherTheme = theme === "dark" ? "Light" : "Dark";

  return (
    <>
      <HeaderMenu
        open={menuOpen}
        onOpenChange={setMenuOpen}
        trigger={<User className="size-4" />}
        triggerLabel={`User menu: ${name}`}
        triggerClassName="px-1.5"
        contentLabel="User menu"
        contentClassName="w-56 gap-1 p-1.5"
      >
        <p className="truncate px-2 py-1 text-sm font-medium">{name}</p>
        {username ? (
          <MenuItem onClick={requestLogOut}>Log out</MenuItem>
        ) : (
          <MenuItem onClick={openLogin}>Log in</MenuItem>
        )}
        <div role="group" aria-labelledby="user-menu-settings" className="mt-1 border-t pt-1">
          <p id="user-menu-settings" className="px-2 py-1 text-xs font-medium text-muted-foreground">
            Settings
          </p>
          {/* Stays open on the item, which then offers the other theme. */}
          <MenuItem onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
            Colour theme: {otherTheme}
          </MenuItem>
        </div>
      </HeaderMenu>

      <LoginDialog open={loginOpen} onOpenChange={setLoginOpen} onSuccess={changedIdentity} />
      <UnsavedWorkDialog
        open={confirmLogOut}
        currentName={openName}
        description="You're logging out."
        onSave={async () => {
          const ok = await unsavedWork.saveAll();
          if (ok) logOut();
          return ok;
        }}
        onDiscard={() => {
          unsavedWork.discardAll();
          logOut();
        }}
        onCancel={() => setConfirmLogOut(false)}
      />
    </>
  );
}

/** A top-level item: the same hover, focus and pressed states as the Cloud Pricing menu's rows. */
function MenuItem({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      {...{ [MENU_ITEM_ATTR]: "" }}
      onClick={onClick}
      className="flex h-8 w-full items-center rounded-md px-2 text-left text-sm transition-colors duration-150 hover:bg-accent focus-visible:bg-accent active:bg-muted"
    >
      {children}
    </button>
  );
}
