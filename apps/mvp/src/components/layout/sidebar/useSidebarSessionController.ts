"use client";

import { useState } from "react";

import { toast } from "@/components/ui/toast";
import { deleteBackendSession } from "@/services/gerclaw/skills";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import type { Session } from "@/types";

export function useSidebarSessionController(onNavigate?: () => void) {
  const role = useAppStore((state) => state.role);
  const currentSessionId = useAppStore((state) => state.currentSessionId);
  const setCurrentSession = useAppStore((state) => state.setCurrentSession);
  const setChatAction = useAppStore((state) => state.setChatAction);
  const setRole = useAppStore((state) => state.setRole);
  const setRightPanel = useAppStore((state) => state.setRightPanel);
  const setPanelContent = useAppStore((state) => state.setPanelContent);
  const closeRightPanel = useAppStore((state) => state.closeRightPanel);
  const setMainView = useAppStore((state) => state.setMainView);
  const sessions = useChatStore((state) => state.sessions);
  const createSession = useChatStore((state) => state.createSession);
  const renameSession = useChatStore((state) => state.renameSession);
  const removeSession = useChatStore((state) => state.removeSession);
  const togglePinSession = useChatStore((state) => state.togglePinSession);
  const [patientHistoryOpen, setPatientHistoryOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<Session | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Session | null>(null);
  const [deletingSession, setDeletingSession] = useState(false);
  const [pendingRole, setPendingRole] = useState<
    "patient" | "doctor" | null
  >(null);
  const isDoctor = role === "doctor";

  const handleNewSession = () => {
    const sessionId = createSession(role);
    setCurrentSession(sessionId);
    setMainView("chat");
    setPanelContent("");
    closeRightPanel();
    onNavigate?.();
  };

  const handleSelectSession = (sessionId: string) => {
    setCurrentSession(sessionId);
    setMainView("chat");
    const session = sessions.find((candidate) => candidate.id === sessionId);
    if (session?.panelType) {
      if (session.panelType === "prescription") {
        setChatAction("prescription");
      }
      setRightPanel(session.panelType);
      setPanelContent(session.panelContent ?? "");
    } else {
      setPanelContent("");
      closeRightPanel();
    }
    onNavigate?.();
  };

  const confirmRoleChange = () => {
    if (!pendingRole) return;
    setRole(pendingRole);
    setPendingRole(null);
    onNavigate?.();
  };

  const openRename = (session: Session) => {
    setRenameTarget(session);
    setRenameTitle(session.title);
  };

  const confirmRename = () => {
    const title = renameTitle.trim();
    if (!renameTarget || !title) return;
    renameSession(renameTarget.id, title);
    setRenameTarget(null);
    toast.show(isDoctor ? "病例会话名称已更新" : "对话名称已更新");
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletingSession(true);
    try {
      await deleteBackendSession(deleteTarget.id);
      const wasCurrentSession = deleteTarget.id === currentSessionId;
      removeSession(deleteTarget.id);
      if (wasCurrentSession) {
        setCurrentSession(null);
        setMainView("chat");
        setPanelContent("");
        closeRightPanel();
      }
      setDeleteTarget(null);
      toast.show(isDoctor ? "病例会话已删除" : "对话已删除");
      onNavigate?.();
    } catch {
      toast.show(
        isDoctor
          ? "暂时无法删除病例会话，请稍后重试。"
          : "暂时无法删除对话，请稍后重试。",
      );
    } finally {
      setDeletingSession(false);
    }
  };

  return {
    sessions,
    currentSessionId,
    patientHistoryOpen,
    setPatientHistoryOpen,
    renameTarget,
    renameTitle,
    setRenameTitle,
    setRenameTarget,
    deleteTarget,
    setDeleteTarget,
    deletingSession,
    pendingRole,
    setPendingRole,
    handleNewSession,
    handleSelectSession,
    confirmRoleChange,
    openRename,
    confirmRename,
    confirmDelete,
    togglePinSession,
  };
}
