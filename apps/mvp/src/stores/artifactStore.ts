import { create } from "zustand";

import type { ArtifactDraftSource } from "@/components/artifact/artifact-draft";

interface ArtifactWorkspaceState {
  source: ArtifactDraftSource | null;
  dirty: boolean;
  openDraft: (source: ArtifactDraftSource) => void;
  setDirty: (dirty: boolean) => void;
  clear: () => void;
}

export const useArtifactStore = create<ArtifactWorkspaceState>((set) => ({
  source: null,
  dirty: false,
  openDraft: (source) => set({ source, dirty: false }),
  setDirty: (dirty) => set({ dirty }),
  clear: () => set({ source: null, dirty: false }),
}));
