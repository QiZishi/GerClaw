import { create } from "zustand";

import type { ArtifactDraftSource } from "@/components/artifact/artifact-draft";

interface ArtifactWorkspaceState {
  source: ArtifactDraftSource | null;
  dirty: boolean;
  openDraft: (source: ArtifactDraftSource) => boolean;
  setDirty: (dirty: boolean) => void;
  clear: () => void;
}

export const UNSAVED_ARTIFACT_MESSAGE =
  "文档仍有未保存的修改。确定放弃这些修改吗？";

export function confirmDiscardArtifactDraft(): boolean {
  const state = useArtifactStore.getState();
  if (!state.dirty) return true;
  return typeof window !== "undefined" && window.confirm(UNSAVED_ARTIFACT_MESSAGE);
}

export const useArtifactStore = create<ArtifactWorkspaceState>((set, get) => ({
  source: null,
  dirty: false,
  openDraft: (source) => {
    const current = get();
    if (
      current.source?.requestId !== source.requestId &&
      !confirmDiscardArtifactDraft()
    ) {
      return false;
    }
    set({ source, dirty: false });
    return true;
  },
  setDirty: (dirty) => set({ dirty }),
  clear: () => set({ source: null, dirty: false }),
}));
