/**
 * 025 (FR-017, research R7): what in the workspace holds input that isn't saved yet, so the app
 * can ask before the agent opens another architecture: "Save and continue" or "Discard and
 * continue". Editors register while they hold unsaved input (today: the Service tab's Save
 * form) and unregister when they don't.
 */
import { useEffect, useRef } from "react";

export type UnsavedSource = {
  id: string;
  /** What holds the input, e.g. "the Service tab". */
  label: string;
  /** Saves it; resolves to false (with the reason shown by the editor) when that fails. */
  save: () => Promise<boolean> | boolean;
  discard: () => void;
};

export class UnsavedWork {
  private sources = new Map<string, UnsavedSource>();

  register(source: UnsavedSource): () => void {
    this.sources.set(source.id, source);
    return () => {
      if (this.sources.get(source.id) === source) this.sources.delete(source.id);
    };
  }

  list(): UnsavedSource[] {
    return [...this.sources.values()];
  }

  get dirty(): boolean {
    return this.sources.size > 0;
  }

  /** Saves every source in turn; stops at the first that fails and returns false. */
  async saveAll(): Promise<boolean> {
    for (const source of this.list()) {
      const ok = await source.save();
      if (ok === false) return false;
    }
    return true;
  }

  discardAll(): void {
    for (const source of this.list()) source.discard();
    this.sources.clear();
  }
}

export const unsavedWork = new UnsavedWork();

/**
 * Registers `id` as unsaved while `dirty` is true. The latest `save`/`discard` are used, so the
 * caller can pass inline functions.
 */
export function useUnsavedWork(
  id: string,
  dirty: boolean,
  label: string,
  save: () => Promise<boolean> | boolean,
  discard: () => void,
  store: UnsavedWork = unsavedWork,
): void {
  const latest = useRef({ save, discard });
  latest.current = { save, discard };
  useEffect(() => {
    if (!dirty) return;
    return store.register({
      id,
      label,
      save: () => latest.current.save(),
      discard: () => latest.current.discard(),
    });
  }, [id, dirty, label, store]);
}
