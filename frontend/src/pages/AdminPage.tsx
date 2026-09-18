import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type AdminUser } from "../api/client";
import { Button } from "../components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { Input } from "../components/ui/input";

/**
 * Admin tab (012-user-accounts-sharing, spec FR-004-013): create/activate/password-manage/
 * purge user accounts. The seeded default Admin account's Active checkbox and purge action
 * are disabled (FR-013) — the backend also enforces this (403), this is just the matching UI
 * affordance.
 */
export function AdminPage() {
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ["adminUsers"], queryFn: api.listAdminUsers });

  const [newUsername, setNewUsername] = useState("");
  const [passwordDialogUserId, setPasswordDialogUserId] = useState<string | null>(null);
  const [passwordInput, setPasswordInput] = useState("");
  const [purgeCandidate, setPurgeCandidate] = useState<AdminUser | null>(null);

  function invalidate() {
    return queryClient.invalidateQueries({ queryKey: ["adminUsers"] });
  }

  const createUser = useMutation({
    mutationFn: (username: string) => api.createAdminUser(username),
    onSuccess: () => {
      setNewUsername("");
      return invalidate();
    },
  });

  const setActive = useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      api.setAdminUserActive(id, isActive),
    onSuccess: invalidate,
  });

  const setPassword = useMutation({
    mutationFn: ({ id, password }: { id: string; password: string }) =>
      api.setAdminUserPassword(id, password),
    onSuccess: () => {
      setPasswordDialogUserId(null);
      setPasswordInput("");
      return invalidate();
    },
  });

  const deleteUser = useMutation({
    mutationFn: (id: string) => api.deleteAdminUser(id),
    onSuccess: () => {
      setPurgeCandidate(null);
      return invalidate();
    },
  });

  return (
    <div className="flex flex-col gap-4 p-4">
      <h1 className="text-sm font-semibold">Admin</h1>

      <table className="w-full max-w-2xl border-collapse text-2xs">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            <th className="py-1.5">Users</th>
            <th className="py-1.5">Active</th>
            <th className="py-1.5">Password</th>
            <th className="py-1.5">Purge</th>
          </tr>
        </thead>
        <tbody>
          {(users.data ?? []).map((user) => (
            <tr key={user.id} className="border-b border-border">
              <td className="py-1.5">{user.username}</td>
              <td className="py-1.5">
                <input
                  type="checkbox"
                  checked={user.is_active}
                  disabled={user.is_default_admin || setActive.isPending}
                  onChange={(e) =>
                    setActive.mutate({ id: user.id, isActive: e.target.checked })
                  }
                  aria-label={`${user.username} active`}
                />
              </td>
              <td className="py-1.5">
                <span className="mr-1.5 font-mono text-muted-foreground">
                  {user.has_password ? `…${user.password_hash_suffix}` : "—"}
                </span>
                <Button
                  variant="outline"
                  size="xs"
                  onClick={() => {
                    setPasswordDialogUserId(user.id);
                    setPasswordInput("");
                  }}
                >
                  {user.has_password ? "Update" : "Create"}
                </Button>
              </td>
              <td className="py-1.5">
                <Button
                  variant="destructive"
                  size="xs"
                  disabled={user.is_default_admin}
                  onClick={() => setPurgeCandidate(user)}
                >
                  Remove user
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <form
        className="flex max-w-sm gap-1.5"
        onSubmit={(e) => {
          e.preventDefault();
          if (newUsername.trim()) createUser.mutate(newUsername.trim());
        }}
      >
        <Input
          value={newUsername}
          onChange={(e) => setNewUsername(e.target.value)}
          placeholder="Username"
          aria-label="New username"
          autoComplete="off"
          data-1p-ignore
          data-lpignore="true"
        />
        <Button type="submit" disabled={!newUsername.trim() || createUser.isPending}>
          Create New User
        </Button>
      </form>
      {createUser.isError && (
        <p className="text-2xs text-destructive">Could not create user — username may already exist.</p>
      )}

      <Dialog
        open={passwordDialogUserId !== null}
        onOpenChange={(open) => !open && setPasswordDialogUserId(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Set password</DialogTitle>
          </DialogHeader>
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (passwordDialogUserId && passwordInput) {
                setPassword.mutate({ id: passwordDialogUserId, password: passwordInput });
              }
            }}
          >
            <Input
              type="password"
              value={passwordInput}
              onChange={(e) => setPasswordInput(e.target.value)}
              placeholder="New password"
              autoFocus
              autoComplete="new-password"
              data-1p-ignore
              data-lpignore="true"
            />
            <DialogFooter>
              <Button type="submit" disabled={!passwordInput || setPassword.isPending}>
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={purgeCandidate !== null} onOpenChange={(open) => !open && setPurgeCandidate(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove {purgeCandidate?.username}?</DialogTitle>
          </DialogHeader>
          <p className="text-2xs text-muted-foreground">
            This permanently removes this user and every architecture they own. This cannot be
            undone.
          </p>
          <DialogFooter>
            <Button
              variant="destructive"
              disabled={deleteUser.isPending}
              onClick={() => purgeCandidate && deleteUser.mutate(purgeCandidate.id)}
            >
              Remove user
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
