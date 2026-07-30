"use client";

import { useEffect, useRef, useState } from "react";

import type { ArtifactDraftSource } from "@/components/artifact/artifact-draft";
import {
  artifactMatchesDraft,
  artifactSaveFailure,
  latestArtifactForRun,
  type ArtifactDraftValue,
  type ArtifactSaveStatus,
} from "@/components/artifact/artifact-save";
import {
  createRunArtifact,
  readConversationArtifacts,
  updateRunArtifact,
} from "@/services/gerclaw/runs";
import type { Artifact } from "@/services/gerclaw/run-contract";
import { backendSessionId } from "@/services/gerclaw/skills";
import { useArtifactStore } from "@/stores/artifactStore";

const SAVE_DELAY_MS = 800;
const pendingArtifactLoads = new Map<string, Promise<Artifact>>();

function loadOrCreateArtifact(source: ArtifactDraftSource): Promise<Artifact> {
  if (!source.runId) throw new Error("run id is required");
  const runId = source.runId;
  const requestKey = `${source.runId}:${source.requestId}`;
  const pending = pendingArtifactLoads.get(requestKey);
  if (pending) return pending;
  const request = readConversationArtifacts(backendSessionId(source.sessionId))
    .then(({ artifacts }) => {
      const existing = latestArtifactForRun(artifacts, runId);
      if (existing) return existing;
      return createRunArtifact(runId, {
        title: source.title,
        markdown: source.markdown,
        kind: "markdown",
      });
    })
    .finally(() => pendingArtifactLoads.delete(requestKey));
  pendingArtifactLoads.set(requestKey, request);
  return request;
}

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
    setStoreDirty(true);
    void loadOrCreateArtifact(source)
      .then((loaded) => {
        if (cancelled) return;
        latestDraftRef.current = { title: loaded.title, markdown: loaded.markdown };
        setTitleState(loaded.title);
        setMarkdownState(loaded.markdown);
        setArtifact(loaded);
        setStatus("saved");
        setStoreDirty(false);
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
    source,
    source.markdown,
    source.runId,
    source.sessionId,
    source.title,
  ]);

  useEffect(() => {
    if (!title.trim()) return;
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
    () => {
      mountedRef.current = true;
      return () => {
        mountedRef.current = false;
      };
    },
    [],
  );

  const updateDraft = (next: ArtifactDraftValue) => {
    latestDraftRef.current = next;
    setTitleState(next.title);
    setMarkdownState(next.markdown);
    setStoreDirty(true);
    const titleValid = Boolean(next.title.trim());
    setErrorMessage(titleValid ? null : "文档标题不能为空。");
    if (!titleValid) {
      setStatus("error");
      return;
    }
    if (artifact) setStatus("dirty");
  };

  const retrySave = async () => {
    setErrorMessage(null);
    if (status === "conflict" && source.runId) {
      setStatus("saving");
      try {
        const { artifacts } = await readConversationArtifacts(
          backendSessionId(source.sessionId),
        );
        const latest = latestArtifactForRun(artifacts, source.runId);
        if (!latest) throw new Error("artifact no longer exists");
        if (!mountedRef.current) return;
        setArtifact(latest);
        setStatus("dirty");
        setStoreDirty(true);
        setRetryNonce((current) => current + 1);
      } catch (error) {
        if (!mountedRef.current) return;
        const failure = artifactSaveFailure(error);
        setStatus(failure.status);
        setErrorMessage(failure.message);
        setStoreDirty(true);
      }
      return;
    }
    setStatus(artifact ? "dirty" : source.runId ? "creating" : "local-only");
    setRetryNonce((current) => current + 1);
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
    retrySave,
  };
}
