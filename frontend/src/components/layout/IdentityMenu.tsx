import { useQuery, useQueryClient } from "@tanstack/react-query";
import { User } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api/client";
import { LoginDialog } from "../auth/LoginDialog";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";

/**
 * Top-left person icon (012-user-accounts-sharing, spec FR-014-019): reflects the current
 * identity (guest vs. named user) and opens the login/change-user flow. Clicking the icon
 * first shows a small "who am I" popup (FR-016/FR-019's distinct Guest/Username states),
 * matching the spec's two-step description, rather than jumping straight to the username
 * form.
 */
export function IdentityMenu() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [loginOpen, setLoginOpen] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const currentUser = useQuery({ queryKey: ["currentUser"], queryFn: api.getCurrentUser });

  function openLogin() {
    setMenuOpen(false);
    setLoginOpen(true);
  }

  function handleLoggedIn() {
    void queryClient.invalidateQueries({ queryKey: ["currentUser"] });
    // A new identity's own data (architectures, admin status) is entirely different from the
    // previous identity's — every architecture-scoped query must refetch, not just currentUser.
    void queryClient.invalidateQueries({ queryKey: ["architectures"] });
    // Follow-up fix: a logged-in-as-Admin session on the Admin tab that then changes to a
    // non-admin user must not leave that route showing — always land the new identity back on
    // Cloud Pricing, regardless of which tab the previous identity was on.
    navigate("/");
  }

  const username = currentUser.data?.username ?? null;

  return (
    <>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={username ? `Logged in as ${username}` : "Guest — click to log in"}
        onClick={() => setMenuOpen(true)}
      >
        <User />
      </Button>

      <Dialog open={menuOpen} onOpenChange={setMenuOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{username ?? "Guest"}</DialogTitle>
          </DialogHeader>
          <DialogFooter>
            <Button onClick={openLogin}>{username ? "Change user" : "Login"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <LoginDialog open={loginOpen} onOpenChange={setLoginOpen} onSuccess={handleLoggedIn} />
    </>
  );
}
