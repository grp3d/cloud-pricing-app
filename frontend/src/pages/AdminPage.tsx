import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  api,
  InvalidImportFileError,
  type AdminUser,
  type AdminUserAgentUpdate,
  type ImportResult,
} from "../api/client";
import { ImportResultsDialog } from "../components/ImportResultsDialog";
import { AdminTabs } from "../components/admin/AdminTabs";
import { AgentSettingsSection } from "../components/admin/AgentSettingsSection";
import { SystemInformationSection } from "../components/admin/SystemInformationSection";
import { Button } from "../components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { buildExportFilename } from "../lib/exportFilename";

/**
 * Admin tab (012-user-accounts-sharing, spec FR-004-013): create/activate/password-manage/
 * purge user accounts. The seeded default Admin account's Active checkbox and purge action
 * are disabled (FR-013) — the backend also enforces this (403), this is just the matching UI
 * affordance.
 *
 * 014-architecture-templates-import-export: per-user Import/Export of architectures to/from the
 * admin's own computer (FR-011-FR-014) — two word-wrapped columns between Password and Purge.
 */
export function AdminPage() {
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ["adminUsers"], queryFn: api.listAdminUsers });

  const [newUsername, setNewUsername] = useState("");
  const [passwordDialogUserId, setPasswordDialogUserId] = useState<string | null>(null);
  const [passwordInput, setPasswordInput] = useState("");
  const [purgeCandidate, setPurgeCandidate] = useState<AdminUser | null>(null);
  // One hidden file input serves every row; this remembers whose Import button opened it.
  const fileInputRef = useRef<HTMLInputElement>(null);
  const importTargetIdRef = useRef<string | null>(null);
  const [importOutcome, setImportOutcome] = useState<{
    results: ImportResult[];
    failedMessage?: string;
  } | null>(null);

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

  // 023 (Story 6): agent access, preview inputs and the monthly limit, per user.
  const updateAgent = useMutation({
    mutationFn: ({ id, update }: { id: string; update: AdminUserAgentUpdate }) =>
      api.updateAdminUserAgent(id, update),
    onSuccess: invalidate,
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

  const exportArchitectures = useMutation({
    mutationFn: async (user: AdminUser) => {
      const doc = await api.exportUserArchitectures(user.id);
      // Saved through the browser's own download — never written server-side (FR-014).
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = buildExportFilename(user.username, new Date());
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    },
  });

  const importArchitectures = useMutation({
    mutationFn: async ({ userId, file }: { userId: string; file: File }) => {
      let doc: unknown;
      try {
        doc = JSON.parse(await file.text());
      } catch {
        return { results: [], failedMessage: "Import failed: the file is not valid JSON." };
      }
      try {
        const response = await api.importUserArchitectures(userId, doc);
        return { results: response.results };
      } catch (error) {
        // A whole-file rejection (400) carries the server's reason; anything else — e.g. a
        // 422 for a body that isn't a JSON object — is still "not in the expected format".
        const reason =
          error instanceof InvalidImportFileError
            ? error.message
            : "the file is not in the expected format";
        return { results: [], failedMessage: `Import failed: ${reason}.` };
      }
    },
    onSuccess: (outcome) => {
      setImportOutcome(outcome);
      return invalidate();
    },
    onError: (error) =>
      setImportOutcome({ results: [], failedMessage: `Import failed: ${error.message}` }),
  });

  function onImportFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    const userId = importTargetIdRef.current;
    // Reset so choosing the same file again still fires `change`; a cancelled picker (no
    // file) does nothing at all.
    e.target.value = "";
    if (file && userId) importArchitectures.mutate({ userId, file });
  }

  const deleteUser = useMutation({
    mutationFn: (id: string) => api.deleteAdminUser(id),
    onSuccess: () => {
      setPurgeCandidate(null);
      return invalidate();
    },
  });

  const userManagement = (
    <section aria-labelledby="user-management-heading" className="flex flex-col gap-4">
      <h2 id="user-management-heading" className="sr-only">
        User Management
      </h2>
      <table className="w-full max-w-5xl border-collapse text-2xs">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            <th className="py-1.5">Users</th>
            <th className="py-1.5">Active</th>
            <th className="py-1.5">Password</th>
            <th className="max-w-[6.5rem] whitespace-normal py-1.5 pr-2 leading-tight">
              Import Architectures from Disk
            </th>
            <th className="max-w-[6.5rem] whitespace-normal py-1.5 pr-2 leading-tight">
              Export Architectures to Disk
            </th>
            <th className="py-1.5">Purge</th>
            {/* 023 (Story 6, FR-019, FR-022a): per-user agent access, preview and limits. */}
            <th className="py-1.5 pl-2">Agent on</th>
            <th className="py-1.5">Preview left</th>
            <th className="py-1.5">Monthly limit</th>
            <th className="py-1.5">This month</th>
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
                  onChange={(e) => setActive.mutate({ id: user.id, isActive: e.target.checked })}
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
                  variant="outline"
                  size="xs"
                  disabled={importArchitectures.isPending}
                  onClick={() => {
                    importTargetIdRef.current = user.id;
                    fileInputRef.current?.click();
                  }}
                >
                  Import
                </Button>
              </td>
              <td className="py-1.5">
                <Button
                  variant="outline"
                  size="xs"
                  disabled={user.architecture_count === 0 || exportArchitectures.isPending}
                  title={user.architecture_count === 0 ? "No architectures to export" : undefined}
                  onClick={() => exportArchitectures.mutate(user)}
                >
                  Export
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
              <td className="py-1.5 pl-2">
                <input
                  type="checkbox"
                  checked={user.agent_enabled_for_user}
                  disabled={updateAgent.isPending}
                  onChange={(e) =>
                    updateAgent.mutate({
                      id: user.id,
                      update: { agent_enabled_for_user: e.target.checked },
                    })
                  }
                  aria-label={`${user.username} agent on`}
                />
              </td>
              <td className="py-1.5">
                <NumberCell
                  label={`${user.username} preview inputs left`}
                  value={user.agent_preview_input_counter}
                  onSave={(n) =>
                    n !== null &&
                    updateAgent.mutate({ id: user.id, update: { agent_preview_input_counter: n } })
                  }
                />
              </td>
              <td className="py-1.5">
                <NumberCell
                  label={`${user.username} monthly limit`}
                  value={user.agent_monthly_input_limit}
                  placeholder={`${user.agent_effective_monthly_limit} (default)`}
                  onSave={(n) =>
                    updateAgent.mutate({
                      id: user.id,
                      update:
                        n === null
                          ? { clear_monthly_input_limit: true }
                          : { agent_monthly_input_limit: n },
                    })
                  }
                />
              </td>
              <td className="py-1.5 whitespace-nowrap">
                {user.agent_inputs_this_month} of {user.agent_effective_monthly_limit}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <input
        ref={fileInputRef}
        type="file"
        accept=".json,application/json"
        className="hidden"
        aria-hidden="true"
        tabIndex={-1}
        onChange={onImportFileChosen}
      />
      <ImportResultsDialog
        open={importOutcome !== null}
        onOpenChange={(open) => !open && setImportOutcome(null)}
        results={importOutcome?.results ?? []}
        failedMessage={importOutcome?.failedMessage}
      />

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
      {exportArchitectures.isError && (
        <p className="text-2xs text-destructive">
          Export failed: {exportArchitectures.error.message}
        </p>
      )}
      {createUser.isError && (
        <p className="text-2xs text-destructive">
          Could not create user — username may already exist.
        </p>
      )}
    </section>
  );

  return (
    <div className="flex flex-col gap-4 p-4">
      <h1 className="text-sm font-semibold">Admin</h1>
      {/* 023: three tabs, so later Admin features each get a place of their own. */}
      <AdminTabs
        tabs={[
          { id: "agent", label: "Agent Settings", content: <AgentSettingsSection /> },
          { id: "users", label: "User Management", content: userManagement },
          { id: "system", label: "System Information", content: <SystemInformationSection /> },
        ]}
      />

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

      <Dialog
        open={purgeCandidate !== null}
        onOpenChange={(open) => !open && setPurgeCandidate(null)}
      >
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

/** 023: a small whole-number field saved on Enter or when it loses focus; blank is null. */
function NumberCell({
  label,
  value,
  placeholder,
  onSave,
}: {
  label: string;
  value: number | null;
  placeholder?: string;
  onSave: (value: number | null) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const shown = draft ?? (value === null ? "" : String(value));
  const commit = () => {
    if (draft === null) return;
    const trimmed = draft.trim();
    const next = trimmed === "" ? null : Number(trimmed);
    setDraft(null);
    if (next !== null && (!Number.isInteger(next) || next < 0)) return;
    if (next !== value) onSave(next);
  };
  return (
    <Input
      type="number"
      min={0}
      step={1}
      aria-label={label}
      className="h-6 w-24 text-2xs"
      value={shown}
      placeholder={placeholder}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") setDraft(null);
      }}
    />
  );
}
