"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { toast } from "@/components/ui/toast";
import { readSessionSkills, replaceSessionSkills } from "@/services/gerclaw/skills";
import { useAppStore } from "@/stores/appStore";

interface SessionSkillSelectionOptions {
  currentSessionId: string | null;
  isGuest: boolean;
}

interface SessionSkillSelection {
  readySessionId: string | null;
  stageSelection: (sessionId: string, skillIds: string[]) => void;
  isReady: (sessionId: string | null) => boolean;
}

/**
 * Restores the owner-scoped Skill selection before a conversation can send.
 *
 * A monotonically increasing load id prevents a slow response from exposing
 * another conversation's selection after the user has switched sessions.
 */
export function useSessionSkillSelection({
  currentSessionId,
  isGuest,
}: SessionSkillSelectionOptions): SessionSkillSelection {
  const setLoadedSkills = useAppStore((state) => state.setLoadedSkills);
  const loadIdRef = useRef(0);
  const pendingSelectionRef = useRef(new Map<string, string[]>());
  const readySessionIdRef = useRef<string | null>(null);
  const [readySessionId, setReadySessionId] = useState<string | null>(null);

  const markReady = useCallback((sessionId: string | null) => {
    readySessionIdRef.current = sessionId;
    setReadySessionId(sessionId);
  }, []);

  const stageSelection = useCallback((sessionId: string, skillIds: string[]) => {
    pendingSelectionRef.current.set(sessionId, [...skillIds]);
  }, []);

  const isReady = useCallback(
    (sessionId: string | null) =>
      isGuest || (sessionId !== null && readySessionIdRef.current === sessionId),
    [isGuest],
  );

  useEffect(() => {
    if (isGuest) {
      loadIdRef.current += 1;
      setLoadedSkills([]);
      readySessionIdRef.current = currentSessionId;
      return;
    }
    if (!currentSessionId) {
      loadIdRef.current += 1;
      setLoadedSkills([]);
      readySessionIdRef.current = null;
      return;
    }

    const sessionId = currentSessionId;
    const loadId = ++loadIdRef.current;
    setLoadedSkills([]);
    readySessionIdRef.current = null;
    const pendingSelection = pendingSelectionRef.current.get(sessionId);
    pendingSelectionRef.current.delete(sessionId);
    const loadSelection = pendingSelection
      ? replaceSessionSkills(sessionId, pendingSelection)
      : readSessionSkills(sessionId);

    void loadSelection
      .then((skillIds) => {
        if (
          loadId === loadIdRef.current &&
          useAppStore.getState().currentSessionId === sessionId
        ) {
          setLoadedSkills(skillIds);
          markReady(sessionId);
        }
      })
      .catch((error) => {
        if (
          loadId === loadIdRef.current &&
          useAppStore.getState().currentSessionId === sessionId
        ) {
          setLoadedSkills([]);
          markReady(sessionId);
          toast.show(error instanceof Error ? error.message : "会话技能未能恢复");
        }
      });
  }, [currentSessionId, isGuest, markReady, setLoadedSkills]);

  return { readySessionId, stageSelection, isReady };
}
