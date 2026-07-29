"use client";

import { useCallback, useState } from "react";

import type { ExitConfirmType } from "@/components/chat/ChatWorkspaceDialogs";
import { stopActiveAudioPlayer } from "@/lib/audioPlaybackCoordinator";
import { fivePrescriptionDraftToMarkdown } from "@/services/gerclaw/prescription-report";
import type { FivePrescriptionDraft } from "@/services/gerclaw/schemas";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import type { ChatActionType, Role } from "@/types";

interface ChatWorkflowControllerOptions {
  chatAction: ChatActionType;
  currentSessionId: string | null;
  role: Role;
}

export function useChatWorkflowController({
  chatAction,
  currentSessionId,
  role,
}: ChatWorkflowControllerOptions) {
  const setCurrentSession = useAppStore((state) => state.setCurrentSession);
  const setChatAction = useAppStore((state) => state.setChatAction);
  const setRightPanel = useAppStore((state) => state.setRightPanel);
  const setPanelContent = useAppStore((state) => state.setPanelContent);
  const createSession = useChatStore((state) => state.createSession);
  const updateSession = useChatStore((state) => state.updateSession);
  const [showExitConfirm, setShowExitConfirm] = useState(false);
  const [exitConfirmType, setExitConfirmType] =
    useState<ExitConfirmType>("cga-server");

  const handlePrescriptionDraftGenerated = useCallback(
    (draft: FivePrescriptionDraft) => {
      const report = fivePrescriptionDraftToMarkdown(draft);
      setRightPanel("prescription");
      setPanelContent(report);
      if (currentSessionId) {
        updateSession(currentSessionId, {
          panelType: "prescription",
          panelContent: report,
        });
      }
    },
    [currentSessionId, setPanelContent, setRightPanel, updateSession],
  );

  const handleStartAction = (action: ChatActionType) => {
    if (action === "none") return;
    if (action === "health-profile") {
      setRightPanel("health-profile");
      return;
    }
    if (
      action === "cga" ||
      action === "chronic-care" ||
      action === "risk-alerts"
    ) {
      setChatAction(action);
      return;
    }
    if (action === "companion") {
      // Never cross ordinary clinical context, Skills or files into companion.
      const companionSessionId = createSession(role);
      setCurrentSession(companionSessionId);
      setChatAction("companion");
      return;
    }
    if (action === "prescription" || action === "drug-review") {
      let sessionId = currentSessionId;
      if (!sessionId) {
        sessionId = createSession(role);
        setCurrentSession(sessionId);
      }
      setChatAction(action);
    }
  };

  const confirmExit = () => {
    setShowExitConfirm(false);
    stopActiveAudioPlayer();
    setChatAction("none");
  };

  const handleExitAction = () => {
    if (chatAction === "cga") {
      setExitConfirmType("cga-server");
      setShowExitConfirm(true);
      return;
    }
    if (chatAction === "drug-review") {
      setExitConfirmType("clinical-intake");
      setShowExitConfirm(true);
      return;
    }
    if (chatAction === "prescription") {
      setExitConfirmType("prescription");
      setShowExitConfirm(true);
      return;
    }
    confirmExit();
  };

  return {
    exitConfirmType,
    showExitConfirm,
    setShowExitConfirm,
    confirmExit,
    handleExitAction,
    handlePrescriptionDraftGenerated,
    handleStartAction,
  };
}
