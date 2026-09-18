import { useState } from "react";

import { api } from "../../api/client";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";
import { Input } from "../ui/input";

type Step = "username" | "create-password" | "enter-password";

/**
 * Login/change-user popup (012-user-accounts-sharing, spec FR-017/FR-018): username, then
 * either "create a password" (no password set yet) or "enter your password" (one exists) —
 * the server (`checkUsername`), not the client, decides which. Any failure (nonexistent
 * username, wrong password, deactivated account) just closes the dialog with no error shown,
 * leaving the current identity exactly as it was (FR-018) — reuses the existing `Dialog`
 * primitive rather than a new modal pattern (research.md §1/§9 precedent).
 */
export function LoginDialog({
  open,
  onOpenChange,
  onSuccess,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}) {
  const [step, setStep] = useState<Step>("username");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  function reset() {
    setStep("username");
    setUsername("");
    setPassword("");
    setIsSubmitting(false);
  }

  function handleOpenChange(next: boolean) {
    onOpenChange(next);
    if (!next) reset();
  }

  async function handleUsernameContinue() {
    if (!username.trim()) return;
    setIsSubmitting(true);
    try {
      const { exists, has_password } = await api.checkUsername(username.trim());
      if (!exists) {
        // FR-018: unknown username fails silently — no error, no state change.
        handleOpenChange(false);
        return;
      }
      setStep(has_password ? "enter-password" : "create-password");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handlePasswordSubmit() {
    if (!password) return;
    setIsSubmitting(true);
    try {
      await api.login(username.trim(), password);
      handleOpenChange(false);
      onSuccess();
    } catch {
      // FR-018: wrong password (or a deactivated account) fails silently.
      handleOpenChange(false);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {step === "username" && "Log in"}
            {step === "create-password" && "Create a password"}
            {step === "enter-password" && "Enter your password"}
          </DialogTitle>
        </DialogHeader>

        {step === "username" && (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void handleUsernameContinue();
            }}
          >
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium" htmlFor="login-username">
                Username
              </label>
              <Input
                id="login-username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
                autoComplete="off"
                data-1p-ignore
                data-lpignore="true"
              />
            </div>
            <DialogFooter>
              <Button type="submit" disabled={!username.trim() || isSubmitting}>
                Continue
              </Button>
            </DialogFooter>
          </form>
        )}

        {(step === "create-password" || step === "enter-password") && (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void handlePasswordSubmit();
            }}
          >
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium" htmlFor="login-password">
                Password
              </label>
              <Input
                id="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoFocus
                autoComplete="new-password"
                data-1p-ignore
                data-lpignore="true"
              />
            </div>
            <DialogFooter>
              <Button type="submit" disabled={!password || isSubmitting}>
                {step === "create-password" ? "Create password & log in" : "Log in"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
