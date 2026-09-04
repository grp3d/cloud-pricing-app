import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { ConfirmDeleteDialog } from "../components/ConfirmDeleteDialog";
import { ErrorMessage } from "../components/ErrorMessage";

function errorMessageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

/**
 * Landing page: provider selector + this provider's Architecture list (FR-003, FR-013, FR-014).
 * Deliberately just the assemble-and-price shell — the price-trend chart and weekly
 * service-count table are out of scope for this feature (spec Assumptions).
 */
export function LandingPage() {
  const queryClient = useQueryClient();
  const [selectedProvider, setSelectedProvider] = useState("aws");
  const [newArchName, setNewArchName] = useState("");
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const providers = useQuery({ queryKey: ["providers"], queryFn: api.listProviders });
  const architectures = useQuery({
    queryKey: ["architectures", selectedProvider],
    queryFn: () => api.listArchitectures(selectedProvider),
  });

  const createArchitecture = useMutation({
    mutationFn: (name: string) => api.createArchitecture(name, selectedProvider),
    onSuccess: () => {
      setNewArchName("");
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["architectures"] });
    },
    onError: (err) => setActionError(errorMessageOf(err)),
  });

  const deleteArchitecture = useMutation({
    mutationFn: (id: string) => api.deleteArchitecture(id),
    onSuccess: () => {
      setPendingDeleteId(null);
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["architectures"] });
    },
    onError: (err) => {
      setPendingDeleteId(null);
      setActionError(errorMessageOf(err));
    },
  });

  const pendingArch = architectures.data?.find((a) => a.id === pendingDeleteId);

  return (
    <main style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h1>Cloud Pricing</h1>

      <section aria-label="Cloud providers">
        <h2>Providers</h2>
        <ul style={{ display: "flex", gap: 12, listStyle: "none", padding: 0 }}>
          {providers.data?.map((p) => (
            <li key={p.code}>
              <button
                disabled={!p.active}
                aria-pressed={p.code === selectedProvider}
                onClick={() => p.active && setSelectedProvider(p.code)}
              >
                {p.name}
                {!p.active && " (coming soon)"}
              </button>
            </li>
          ))}
        </ul>
      </section>

      {actionError && (
        <ErrorMessage message={actionError} onRetry={() => setActionError(null)} retryLabel="Dismiss" />
      )}

      <section aria-label="Architectures">
        <h2>{selectedProvider.toUpperCase()} Architectures</h2>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (newArchName.trim()) createArchitecture.mutate(newArchName.trim());
          }}
        >
          <input
            value={newArchName}
            onChange={(e) => setNewArchName(e.target.value)}
            placeholder="New architecture name"
            aria-label="New architecture name"
          />
          <button type="submit" disabled={createArchitecture.isPending}>
            Create
          </button>
        </form>

        {architectures.isLoading && <p>Loading…</p>}
        {architectures.isError && (
          <ErrorMessage
            message={errorMessageOf(architectures.error)}
            onRetry={() => architectures.refetch()}
          />
        )}
        {!architectures.isError && architectures.data?.length === 0 && (
          <p>No architectures yet — create one above.</p>
        )}

        <ul>
          {architectures.data?.map((arch) => (
            <li key={arch.id}>
              <Link to={`/architectures/${arch.id}`}>{arch.name}</Link>{" "}
              <button onClick={() => setPendingDeleteId(arch.id)} aria-label={`Delete ${arch.name}`}>
                ✕
              </button>
            </li>
          ))}
        </ul>
      </section>

      {pendingArch && (
        <ConfirmDeleteDialog
          itemLabel={pendingArch.name}
          onCancel={() => setPendingDeleteId(null)}
          onConfirm={() => deleteArchitecture.mutate(pendingArch.id)}
        />
      )}
    </main>
  );
}
