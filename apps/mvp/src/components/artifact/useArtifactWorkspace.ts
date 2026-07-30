"use client";

import { useEffect, useRef, useState } from "react";

import type { ArtifactDraftSource } from "@/components/artifact/artifact-draft";
import {
  artifactMatchesDraft,
  artifactSaveFailure,
  type ArtifactDraftValue,
  type ArtifactSaveStatus,
} from "@/components/artifact/artifact-save";
import {
  createRunArtifact,
  updateRunArtifact,
} from "@/services/gerclaw/runs";
import type { Artifact } from "@/services/gerclaw/run-contract";
import { useArtifactStore } from "@/stores/artifactStore";

const SAVE_DELAY_MS = 800;

export function useArtifactWorkspace(source: ArtifactDraftSource) {
  const setStoreDirty = useArtifactStore((state) => state.setDirty);
  const [title, setTitleState] = useState(source.title);
  const [markdown, setMarkdownState] = useState(source.markdown);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [status, setStatus] = useState<ArtifactSaveStatus>(
    source.runId ? "creating" : "local-only",
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  const latestDraftRef = useRef<ArtifactDraftValue>({
    title: source.title,
    markdown: source.markdown,
  });
  const saveInFlightRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    if (!source.runId) {
      setStoreDirty(true);
      return;
    }
    if (artifact) return;
    let cancelled = false;
    void createRunArtifact(source.runId, {
      title: source.title,
      markdown: source.markdown,
      kind: "markdown",
    })
      .then((created) => {
        if (cancelled) return;
        setArtifact(created);
        if (artifactMatchesDraft(created, latestDraftRef.current)) {
          setStatus("saved");
          setStoreDirty(false);
        } else {
          setStatus("dirty");
          setStoreDirty(true);
        }
      })
      .catch((error) => {
        if (cancelled) return;
        const failure = artifactSaveFailure(error);
        setStatus(failure.status);
        setErrorMessage(failure.message);
        setStoreDirty(true);
      });
    return () => {
      cancelled = true;
    };
  }, [
    artifact,
    retryNonce,
    setStoreDirty,
    source.markdown,
    source.runId,
    source.title,
  ]);

  useEffect(() => {
    if (!artifact || artifactMatchesDraft(artifact, { title, markdown })) return;
    const timer = setTimeout(() => {
      if (saveInFlightRef.current) return;
      saveInFlightRef.current = true;
      const submittedDraft = { title, markdown };
      setStatus("saving");
      setErrorMessage(null);
      void updateRunArtifact(artifact.id, {
        ...submittedDraft,
        kind: artifact.kind,
        expected_revision: artifact.revision,
      })
        .then((saved) => {
          if (!mountedRef.current) return;
          setArtifact(saved);
          if (artifactMatchesDraft(saved, latestDraftRef.current)) {
            setStatus("saved");
            setStoreDirty(false);
          } else {
            setStatus("dirty");
            setStoreDirty(true);
          }
        })
        .catch((error) => {
          if (!mountedRef.current) return;
          const failure = artifactSaveFailure(error);
          setStatus(failure.status);
          setErrorMessage(failure.message);
          setStoreDirty(true);
        })
        .finally(() => {
          saveInFlightRef.current = false;
        });
    }, SAVE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [artifact, markdown, retryNonce, setStoreDirty, title]);

  useEffect(() => {
    const protectUnsavedDraft = (event: BeforeUnloadEvent) => {
      if (!useArtifactStore.getState().dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", protectUnsavedDraft);
    return () => window.removeEventListener("beforeunload", protectUnsavedDraft);
  }, []);

  useEffect(
    () => () => {
      mountedRef.current = false;
    },
    [],
  );

  const updateDraft = (next: ArtifactDraftValue) => {
    latestDraftRef.current = next;
    setTitleState(next.title);
    setMarkdownState(next.markdown);
    setStoreDirty(true);
    setErrorMessage(null);
    if (artifact) setStatus("dirty");
  };

  return {
    source,
    artifact,
    title,
    markdown,
    status,
    errorMessage,
    setTitle: (nextTitle: string) =>
      updateDraft({ title: nextTitle, markdown: latestDraftRef.current.markdown }),
    setMarkdown: (nextMarkdown: string) =>
      updateDraft({ title: latestDraftRef.current.title, markdown: nextMarkdown }),
    retrySave: () => {
      setErrorMessage(null);
      setStatus(artifact ? "dirty" : source.runId ? "creating" : "local-only");
      setRetryNonce((current) => current + 1);
    },
  };
}
