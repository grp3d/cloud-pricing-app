/**
 * 023-agent-foundation (Story 5, FR-016–FR-018, FR-022a): the Admin's agent settings. Changes
 * take effect from the next message, with no redeploy. The hosted model's key is never shown,
 * only whether one is set; this month's spend shows against the global cap.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  api,
  ApiStatusError,
  type AgentSettings,
  type AgentSettingsUpdate,
} from "../../api/client";
import { formatResetDate } from "../agent/agentText";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

type Form = {
  agent_enabled: boolean;
  agent_provider: AgentSettingsUpdate["agent_provider"];
  agent_model: string;
  agent_base_url: string;
  agent_timeout_seconds: string;
  agent_global_monthly_cap_usd: string;
  agent_default_user_monthly_inputs: string;
  agent_price_per_input_token_usd: string;
  agent_price_per_output_token_usd: string;
};

function toForm(s: AgentSettings): Form {
  return {
    agent_enabled: s.agent_enabled,
    agent_provider: s.agent_provider,
    agent_model: s.agent_model ?? "",
    agent_base_url: s.agent_base_url,
    agent_timeout_seconds: String(s.agent_timeout_seconds),
    agent_global_monthly_cap_usd: String(s.agent_global_monthly_cap_usd),
    agent_default_user_monthly_inputs: String(s.agent_default_user_monthly_inputs),
    agent_price_per_input_token_usd: s.agent_price_per_input_token_usd ?? "",
    agent_price_per_output_token_usd: s.agent_price_per_output_token_usd ?? "",
  };
}

function toUpdate(f: Form): AgentSettingsUpdate {
  return {
    agent_enabled: f.agent_enabled,
    agent_provider: f.agent_provider,
    agent_model: f.agent_model.trim() || null,
    agent_base_url: f.agent_base_url.trim(),
    agent_timeout_seconds: Number(f.agent_timeout_seconds),
    agent_global_monthly_cap_usd: f.agent_global_monthly_cap_usd.trim(),
    agent_default_user_monthly_inputs: Number(f.agent_default_user_monthly_inputs),
    agent_price_per_input_token_usd: f.agent_price_per_input_token_usd.trim() || null,
    agent_price_per_output_token_usd: f.agent_price_per_output_token_usd.trim() || null,
  };
}

/** `422` field messages from the server, by field name. */
function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiStatusError) || !Array.isArray(error.detail)) return {};
  const out: Record<string, string> = {};
  for (const item of error.detail as { loc?: unknown[]; msg?: string }[]) {
    const field = item.loc?.[item.loc.length - 1];
    if (typeof field === "string") out[field] = item.msg ?? "Invalid value";
  }
  return out;
}

export function AgentSettingsSection() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["agentSettings"], queryFn: api.getAgentSettings });
  const [form, setForm] = useState<Form | null>(null);
  useEffect(() => {
    if (settings.data && form === null) setForm(toForm(settings.data));
  }, [settings.data, form]);

  const save = useMutation({
    mutationFn: (f: Form) => api.updateAgentSettings(toUpdate(f)),
    onSuccess: (saved) => {
      queryClient.setQueryData(["agentSettings"], saved);
      setForm(toForm(saved));
      void queryClient.invalidateQueries({ queryKey: ["agentStatus"] });
      void queryClient.invalidateQueries({ queryKey: ["adminUsers"] });
    },
  });
  const errors = fieldErrors(save.error);

  if (!settings.data || !form) {
    return (
      <section aria-labelledby="agent-settings-heading">
        <h2 id="agent-settings-heading" className="sr-only">
          Agent settings
        </h2>
        <p className="text-2xs text-muted-foreground">Loading…</p>
      </section>
    );
  }
  const set = <K extends keyof Form>(key: K, value: Form[K]) =>
    setForm((f) => (f ? { ...f, [key]: value } : f));

  const field = (key: keyof Form, label: string, hint?: string, type = "text") => (
    <label className="flex flex-col gap-0.5">
      <span>{label}</span>
      <Input
        type={type}
        value={String(form[key])}
        onChange={(e) => set(key, e.target.value as never)}
        aria-invalid={Boolean(errors[key])}
        aria-describedby={errors[key] ? `${key}-error` : undefined}
        className="h-7 text-2xs"
      />
      {hint && <span className="text-muted-foreground">{hint}</span>}
      {errors[key] && (
        <span id={`${key}-error`} className="text-destructive">
          {errors[key]}
        </span>
      )}
    </label>
  );

  return (
    <section aria-labelledby="agent-settings-heading" className="flex flex-col gap-2">
      <h2 id="agent-settings-heading" className="sr-only">
        Agent settings
      </h2>
      <form
        className="grid max-w-2xl grid-cols-2 gap-x-4 gap-y-2 text-2xs"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(form);
        }}
      >
        <label className="col-span-2 flex items-center gap-2">
          <input
            type="checkbox"
            checked={form.agent_enabled}
            onChange={(e) => set("agent_enabled", e.target.checked)}
          />
          Agent on
          {errors.agent_enabled && <span className="text-destructive">{errors.agent_enabled}</span>}
        </label>
        <label className="flex flex-col gap-0.5">
          <span>Provider</span>
          <select
            className="focus-ring h-7 rounded-md border border-input bg-background px-2"
            value={form.agent_provider}
            onChange={(e) => set("agent_provider", e.target.value as Form["agent_provider"])}
            aria-invalid={Boolean(errors.agent_provider)}
          >
            <option value="ollama">Ollama (local)</option>
            <option value="anthropic">Anthropic (hosted)</option>
            {form.agent_provider === "scripted" && (
              <option value="scripted">Scripted (test)</option>
            )}
          </select>
          {errors.agent_provider && (
            <span className="text-destructive">{errors.agent_provider}</span>
          )}
        </label>
        {field("agent_model", "Model", "For example claude-haiku-5-5, or a local model's name.")}
        {field("agent_base_url", "Local model address", "Used for Ollama only.")}
        {field("agent_timeout_seconds", "Timeout (seconds)", "5 to 600.", "number")}
        {field("agent_global_monthly_cap_usd", "Global monthly cap (USD)")}
        {field(
          "agent_default_user_monthly_inputs",
          "Default monthly messages per user",
          undefined,
          "number",
        )}
        {field(
          "agent_price_per_input_token_usd",
          "Price per input token (USD)",
          "Hosted model only.",
        )}
        {field(
          "agent_price_per_output_token_usd",
          "Price per output token (USD)",
          "Hosted model only.",
        )}
        <dl className="col-span-2 flex flex-wrap gap-x-6 gap-y-1">
          <div>
            <dt className="inline text-muted-foreground">API key set: </dt>
            <dd className="inline">{settings.data.api_key_set ? "yes" : "no"}</dd>
          </div>
          <div>
            <dt className="inline text-muted-foreground">This month: </dt>
            <dd className="inline">
              ${Number(settings.data.spend_this_month_usd).toFixed(2)} of $
              {Number(settings.data.agent_global_monthly_cap_usd).toFixed(2)} (resets{" "}
              {formatResetDate(settings.data.resets_on)})
            </dd>
          </div>
        </dl>
        <div className="col-span-2 flex items-center gap-2">
          <Button type="submit" size="sm" disabled={save.isPending}>
            Save agent settings
          </Button>
          {save.isSuccess && <span className="text-muted-foreground">Saved.</span>}
          {save.isError && Object.keys(errors).length === 0 && (
            <span className="text-destructive">{(save.error as Error).message}</span>
          )}
        </div>
      </form>
    </section>
  );
}
