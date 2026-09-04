import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { ConfirmDeleteDialog } from "../components/ConfirmDeleteDialog";

/**
 * Landing page: provider selector + this provider's Architecture list (FR-003, FR-013, FR-014).
 * Deliberately just the assemble-and-price shell — the price-trend chart and weekly
 * service-count table are out of scope for this feature (spec Assumptions).
 */
export function LandingPage() {
  const queryClient = useQueryClient();
  const [newArchName, setNewArchName] = useState("");
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const providers = useQuery({ queryKey: ["providers"], queryFn: api.listProviders });
  const architectures = useQuery({
    queryKey: ["architectures", "aws"],
    queryFn: () => api.listArchitectures("aws"),
  });

  const createArchitecture = useMutation({
    mutationFn: (name: string) => api.createArchitecture(name, "aws"),
    onSuccess: () => {
      setNewArchName("");
      queryClient.invalidateQueries({ queryKey: ["architectures"] });
    },
  });

  const deleteArchitecture = useMutation({
    mutationFn: (id: string) => api.deleteArchitecture(id),
    onSuccess: () => {
      setPendingDeleteId(null);
      queryClient.invalidateQueries({ queryKey: ["architectures"] });
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
              <button disabled={!p.active} aria-pressed={p.code === "aws"}>
                {p.name}
                {!p.active && " (coming soon)"}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Architectures">
        <h2>AWS Architectures</h2>

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
        {architectures.data?.length === 0 && <p>No architectures yet — create one above.</p>}

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
