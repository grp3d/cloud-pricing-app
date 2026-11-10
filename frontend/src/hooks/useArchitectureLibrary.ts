/**
 * The user's architecture list and its actions (021, research R2), shared by the header's
 * architecture menu on every page. This is what Column 1 owned before 021, moved out of
 * `WorkspacePage` so the menu works on Trends and Admin too.
 *
 * - One list query per provider, under the same `["architectures", provider]` keys as before,
 *   so every existing `invalidateQueries({ queryKey: ["architectures"] })` still refreshes it.
 * - Deleting keeps 015's side effect (the stored pricing result goes too) and leaves the
 *   workspace when the open architecture is the one deleted.
 * - Import lists only one provider's public architectures (`?provider=`, research R12).
 */
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useMatch, useNavigate } from "react-router-dom";

import { type ArchitectureSummary, type Provider, type ProviderCode, api } from "../api/client";
import { removePricingResult } from "../lib/architecturePricingResults";
import { asProviderCode } from "../lib/providerPricing";

/** Display order of the menu's groups (FR-001); any other provider follows, as listed. */
const PROVIDER_ORDER: readonly string[] = ["aws", "gcp", "azure"];

function errorMessageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

export interface ProviderArchitectures {
  provider: Provider;
  architectures: ArchitectureSummary[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useArchitectureLibrary({ onNavigated }: { onNavigated?: () => void } = {}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const activeArchitectureId =
    useMatch("/architectures/:architectureId")?.params.architectureId ?? undefined;

  const providersQuery = useQuery({ queryKey: ["providers"], queryFn: api.listProviders });
  const providers = [...(providersQuery.data ?? [])].sort((a, b) => {
    const ia = PROVIDER_ORDER.indexOf(a.code);
    const ib = PROVIDER_ORDER.indexOf(b.code);
    return (ia === -1 ? PROVIDER_ORDER.length : ia) - (ib === -1 ? PROVIDER_ORDER.length : ib);
  });

  const lists = useQueries({
    queries: providers.map((p) => ({
      queryKey: ["architectures", p.code],
      queryFn: () => api.listArchitectures(p.code),
    })),
  });
  const groups: ProviderArchitectures[] = providers.map((provider, i) => ({
    provider,
    architectures: lists[i]?.data ?? [],
    isLoading: lists[i]?.isLoading ?? true,
    error: lists[i]?.isError ? errorMessageOf(lists[i].error) : null,
    refetch: () => void lists[i]?.refetch(),
  }));

  // Same query key `IdentityMenu` uses, so this costs no extra request. Guests never get the
  // sharing or Import actions (012, FR-022/FR-027).
  const currentUser = useQuery({ queryKey: ["currentUser"], queryFn: api.getCurrentUser });
  const isGuest = currentUser.data?.username == null;

  const [actionError, setActionError] = useState<string | null>(null);

  function open(id: string) {
    navigate(`/architectures/${id}`);
    onNavigated?.();
  }

  const createArchitecture = useMutation({
    mutationFn: ({ name, provider }: { name: string; provider: ProviderCode }) =>
      api.createArchitecture(name, provider),
    onSuccess: (arch) => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["architectures"] });
      open(arch.id);
    },
    onError: (err) => setActionError(errorMessageOf(err)),
  });

  const [pendingDelete, setPendingDelete] = useState<ArchitectureSummary | null>(null);
  const deleteArchitecture = useMutation({
    mutationFn: (id: string) => api.deleteArchitecture(id),
    onSuccess: (_data, id) => {
      setPendingDelete(null);
      setActionError(null);
      // 015-canvas-service-icons, spec Edge Cases: a deleted Architecture's stored result goes too.
      removePricingResult(id);
      queryClient.invalidateQueries({ queryKey: ["architectures"] });
      if (activeArchitectureId === id) navigate("/");
    },
    onError: (err) => {
      setPendingDelete(null);
      setActionError(errorMessageOf(err));
    },
  });

  // 012-user-accounts-sharing, spec FR-020: owner-only public/private toggle.
  const togglePublic = useMutation({
    mutationFn: ({ id, isPublic }: { id: string; isPublic: boolean }) =>
      api.setArchitecturePublic(id, isPublic),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["architectures"] }),
    onError: (err) => setActionError(errorMessageOf(err)),
  });

  const [importProvider, setImportProvider] = useState<ProviderCode | null>(null);
  const importable = useQuery({
    queryKey: ["importableArchitectures", importProvider],
    // Never `queryFn: api.listImportableArchitectures`: React Query would pass its context
    // object as the provider.
    queryFn: () => api.listImportableArchitectures(importProvider ?? undefined),
    enabled: importProvider !== null,
  });
  const renameArchitecture = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => api.renameArchitecture(id, name),
    onSuccess: (_data, { id }) => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["architectures"] });
      queryClient.invalidateQueries({ queryKey: ["architecture", id] });
    },
    onError: (err) => setActionError(errorMessageOf(err)),
  });

  const importArchitecture = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => api.importArchitecture(id, name),
    onSuccess: () => {
      setImportProvider(null);
      queryClient.invalidateQueries({ queryKey: ["architectures"] });
    },
    onError: (err) => setActionError(errorMessageOf(err)),
  });

  return {
    groups,
    providersLoading: providersQuery.isLoading,
    activeArchitectureId,
    isGuest,
    actionError,
    dismissActionError: () => setActionError(null),
    open,
    create: (provider: string, name: string) =>
      createArchitecture.mutate({ name, provider: asProviderCode(provider) }),
    creatingProvider: createArchitecture.isPending
      ? (createArchitecture.variables?.provider ?? null)
      : null,
    togglePublic: (id: string, isPublic: boolean) => togglePublic.mutate({ id, isPublic }),
    /** 021 (FR-043): resolves once the rename is saved (or has failed). */
    rename: (id: string, name: string) =>
      renameArchitecture.mutateAsync({ id, name }).then(
        () => true,
        () => false,
      ),
    pendingDelete,
    requestDelete: setPendingDelete,
    cancelDelete: () => setPendingDelete(null),
    confirmDelete: () => pendingDelete && deleteArchitecture.mutate(pendingDelete.id),
    importProvider,
    openImport: (provider: string) => setImportProvider(asProviderCode(provider)),
    closeImport: () => setImportProvider(null),
    importable: importable.data,
    importArchitecture: (id: string, name: string) => importArchitecture.mutate({ id, name }),
    isImporting: importArchitecture.isPending,
  };
}

export type ArchitectureLibrary = ReturnType<typeof useArchitectureLibrary>;
