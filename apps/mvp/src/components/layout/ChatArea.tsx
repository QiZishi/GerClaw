"use client";

import { useEffect, useState } from "react";

import { ChatWorkspaceDialogs } from "@/components/chat/ChatWorkspaceDialogs";
import { ChatWorkspaceView } from "@/components/chat/ChatWorkspaceView";
import { useAgentConversationStream } from "@/components/chat/useAgentConversationStream";
import { useChatWorkflowController } from "@/components/chat/useChatWorkflowController";
import { useConversationHistoryRecovery } from "@/components/chat/useConversationHistoryRecovery";
import { useConversationController } from "@/components/chat/useConversationController";
import { useSessionSkillSelection } from "@/components/chat/useSessionSkillSelection";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import { toast } from "@/components/ui/toast";
import type { Message } from "@/types";

/**
 * §3.3 中间聊天区
 * 弹性宽度，根据 mainView 切换显示聊天或技能管理
 * - mainView='chat'：无消息显示欢迎页，否则显示消息列表 + 输入框
 * - mainView='skills'：显示技能管理（对齐 Trae Work）
 * - chatAction：对话式功能流程（AI 通过聊天收集用户信息，自动提取+追问）
 */
export function ChatArea() {
  const role = useAppStore((s) => s.role);
  const isGuest = useAppStore((s) => s.isGuest);
  const currentSessionId = useAppStore((s) => s.currentSessionId);
  const mainView = useAppStore((s) => s.mainView);
  const setMainView = useAppStore((s) => s.setMainView);
  const chatAction = useAppStore((s) => s.chatAction);
  const setChatAction = useAppStore((s) => s.setChatAction);
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const isGenerating = useChatStore((s) => s.isGenerating);
  const messagesBySession = useChatStore((s) => s.messagesBySession);
  const deleteMessage = useChatStore((s) => s.deleteMessage);
  const storeSessions = useChatStore((s) => s.sessions);

  const { sendTurn: doSend, stopTurn: handleStop } =
    useAgentConversationStream();
  const {
    readySessionId: skillSelectionReadySessionId,
    stageSelection: stageSkillSelection,
    isReady: isSkillSelectionReady,
  } = useSessionSkillSelection({ currentSessionId, isGuest });
  const {
    handleAnswerVersionSelected,
    handleRegenerate,
    handleSend,
  } = useConversationController({
    currentSessionId,
    chatAction,
    role,
    sendTurn: doSend,
    stageSkillSelection,
    isSkillSelectionReady,
  });
  useConversationHistoryRecovery({
    currentSessionId,
    isGuest,
    contextReadySessionId: skillSelectionReadySessionId,
    sendTurn: doSend,
  });
  const {
    exitConfirmType,
    showExitConfirm,
    setShowExitConfirm,
    confirmExit,
    handleExitAction,
    handlePrescriptionDraftGenerated,
    handleStartAction,
  } = useChatWorkflowController({ chatAction, currentSessionId, role });

  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
  }, []);

  // 消息导出/分享弹窗：值为触发的消息 id（用于默认选中），null 表示关闭
  const [exportMessageId, setExportMessageId] = useState<string | null>(null);
  // 消息删除确认弹窗：值为待删除的消息 id，null 表示关闭
  const [deleteMessageId, setDeleteMessageId] = useState<string | null>(null);



  const messages: Message[] = currentSessionId
    ? messagesBySession[currentSessionId] ?? []
    : [];

  const currentSession = currentSessionId
    ? storeSessions.find((session) => session.id === currentSessionId)
    : undefined;
  const currentSessionTitle = currentSession?.title ?? "";

  // 仅健康画像由右侧面板承载；其余入口均由各自的真实后端流程承载。
  useEffect(() => {
    if (chatAction === "none" || chatAction === "companion" || chatAction === "cga" || chatAction === "prescription" || chatAction === "drug-review" || chatAction === "chronic-care" || chatAction === "risk-alerts") return;
    setChatAction("none");
  }, [chatAction, setChatAction]);

  /** 请求删除消息 - 显示确认对话框 */
  const handleDeleteRequest = (messageId: string) => {
    setDeleteMessageId(messageId);
  };

  /** 确认删除消息 */
  const handleDeleteConfirm = () => {
    if (deleteMessageId) {
      deleteMessage(deleteMessageId);
      toast.show("消息已删除");
    }
    setDeleteMessageId(null);
  };

  /** 取消删除 */
  const handleDeleteCancel = () => {
    setDeleteMessageId(null);
  };

  const handleExampleClick = (text: string) => {
    handleSend(text);
  };

  return (
    <>
      <ChatWorkspaceView
        mounted={mounted}
        mainView={mainView}
        chatAction={chatAction}
        role={role}
        seniorMode={seniorMode}
        sidebarCollapsed={sidebarCollapsed}
        currentSessionId={currentSessionId}
        currentSessionTitle={currentSessionTitle}
        hasExistingPrescriptionDraft={
          currentSession?.panelType === "prescription" &&
          Boolean(currentSession.panelContent)
        }
        messages={messages}
        isGenerating={isGenerating}
        contextLoading={Boolean(
          chatAction !== "companion" &&
            !isGuest &&
            currentSessionId &&
            skillSelectionReadySessionId !== currentSessionId,
        )}
        onReturnToChat={() => setMainView("chat")}
        onExampleClick={handleExampleClick}
        onStartAction={handleStartAction}
        onExitAction={handleExitAction}
        onPrescriptionDraftGenerated={handlePrescriptionDraftGenerated}
        onRegenerate={handleRegenerate}
        onShare={setExportMessageId}
        onDelete={handleDeleteRequest}
        onAnswerVersionSelected={handleAnswerVersionSelected}
        onSend={handleSend}
        onStop={handleStop}
      />
      <ChatWorkspaceDialogs
        messages={messages}
        seniorMode={seniorMode}
        exportMessageId={exportMessageId}
        deleteMessageId={deleteMessageId}
        showExitConfirm={showExitConfirm}
        exitConfirmType={exitConfirmType}
        onCloseExport={() => setExportMessageId(null)}
        onCloseDelete={handleDeleteCancel}
        onConfirmDelete={handleDeleteConfirm}
        onExitOpenChange={setShowExitConfirm}
        onConfirmExit={confirmExit}
      />
    </>
  );
}
