"use client";

import {
  useCallback,
  useEffect,
  useState,
} from "react";

import type { ChatDocumentAttachment } from "@/components/chat/ChatInput";
import {
  ChatWorkspaceDialogs,
  type ExitConfirmType,
} from "@/components/chat/ChatWorkspaceDialogs";
import { ChatWorkspaceView } from "@/components/chat/ChatWorkspaceView";
import { useAgentConversationStream } from "@/components/chat/useAgentConversationStream";
import { useConversationHistoryRecovery } from "@/components/chat/useConversationHistoryRecovery";
import { useSessionSkillSelection } from "@/components/chat/useSessionSkillSelection";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import {
  toFrontendCitation,
} from "@/services/gerclaw/conversation-history";
import { registerParsedDocument } from "@/services/gerclaw/documents";
import { fivePrescriptionDraftToMarkdown } from "@/services/gerclaw/prescription-report";
import type { FivePrescriptionDraft } from "@/services/gerclaw/schemas";
import type { AnswerVersion } from "@/services/gerclaw/run-contract";
import { toast } from "@/components/ui/toast";
import { stopActiveAudioPlayer } from "@/lib/audioPlaybackCoordinator";
import type { ChatActionType, ImageAttachment, Message, MessageBlock } from "@/types";

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
  const setCurrentSession = useAppStore((s) => s.setCurrentSession);
  const mainView = useAppStore((s) => s.mainView);
  const setMainView = useAppStore((s) => s.setMainView);
  const chatAction = useAppStore((s) => s.chatAction);
  const setChatAction = useAppStore((s) => s.setChatAction);
  const setRightPanel = useAppStore((s) => s.setRightPanel);
  const setPanelContent = useAppStore((s) => s.setPanelContent);
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const loadedSkillIds = useAppStore((s) => s.loadedSkillIds);
  const isGenerating = useChatStore((s) => s.isGenerating);
  const messagesBySession = useChatStore((s) => s.messagesBySession);
  const updateMessage = useChatStore((s) => s.updateMessage);
  const deleteMessage = useChatStore((s) => s.deleteMessage);
  const updateSession = useChatStore((s) => s.updateSession);
  const createSession = useChatStore((s) => s.createSession);
  const storeSessions = useChatStore((s) => s.sessions);

  const { sendTurn: doSend, stopTurn: handleStop } =
    useAgentConversationStream();
  const {
    readySessionId: skillSelectionReadySessionId,
    stageSelection: stageSkillSelection,
    isReady: isSkillSelectionReady,
  } = useSessionSkillSelection({ currentSessionId, isGuest });
  useConversationHistoryRecovery({
    currentSessionId,
    isGuest,
    contextReadySessionId: skillSelectionReadySessionId,
    sendTurn: doSend,
  });

  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
  }, []);

  // Only workflows with a durable interruption consequence need confirmation.
  const [showExitConfirm, setShowExitConfirm] = useState(false);
  const [exitConfirmType, setExitConfirmType] =
    useState<ExitConfirmType>("cga-server");
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

  /** 从消息中提取纯文本内容 */
  const getTextFromMessage = (msg: Message): string => {
    return msg.blocks
      .filter((b): b is Extract<MessageBlock, { kind: "text" }> => b.kind === "text")
      .map((b) => b.content)
      .join("\n");
  };

  // 仅健康画像由右侧面板承载；其余入口均由各自的真实后端流程承载。
  useEffect(() => {
    if (chatAction === "none" || chatAction === "companion" || chatAction === "cga" || chatAction === "prescription" || chatAction === "drug-review" || chatAction === "chronic-care" || chatAction === "risk-alerts") return;
    setChatAction("none");
  }, [chatAction, setChatAction]);

  /** 重新生成 */
  const handleRegenerate = (messageId: string) => {
    if (!currentSessionId) return;
    const messages = messagesBySession[currentSessionId] ?? [];
    const aiMsgIndex = messages.findIndex((m) => m.id === messageId);
    if (aiMsgIndex === -1) return;
    
    let userMsgIndex = aiMsgIndex - 1;
    while (userMsgIndex >= 0 && messages[userMsgIndex].role !== "user") {
      userMsgIndex--;
    }
    if (userMsgIndex < 0) return;
    
    const userMsg = messages[userMsgIndex];
    const currentAnswer = messages[aiMsgIndex];
    if (!currentAnswer.answerGroupRunId || !currentAnswer.answerVersionId) {
      toast.show("请刷新对话以恢复服务端回答版本后再重新生成");
      return;
    }
    const assistantWorkflow = messages[aiMsgIndex]?.workflow ?? "standard";
    const userText = getTextFromMessage(userMsg);
    const userImages: ImageAttachment[] = userMsg.blocks
      .filter((b): b is Extract<MessageBlock, { kind: "image" }> => b.kind === "image")
      .map((b) => b.data);
    
    doSend(
      currentSessionId,
      userText,
      true,
      userImages.length > 0 ? userImages : undefined,
      userMsg.uploadedFiles ?? [],
      assistantWorkflow,
      [],
      {
        sourceRunId: currentAnswer.answerGroupRunId,
        expectedCurrentAnswerVersionId: currentAnswer.answerVersionId,
      },
      messageId,
      currentAnswer
    );
  };

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

  const handleAnswerVersionSelected = async (
    sessionId: string,
    messageId: string,
    version: AnswerVersion,
  ) => {
    if (!version.answer_markdown) {
      throw new Error("该回答版本正文已不可用");
    }
    const target = useChatStore.getState().getMessages(sessionId)
      .find((message) => message.id === messageId);
    if (!target) return;
    updateMessage(messageId, {
      blocks: [{
        kind: "text",
        id: `block_${messageId}_${version.id}`,
        content: version.answer_markdown,
      }],
      citations: version.citations.map(toFrontendCitation),
      answerGroupRunId: version.run_id,
      answerVersionId: version.id,
      answerVersion: version.version,
      executionRunId: version.producer_run_id,
      feedback: null,
      feedbackText: undefined,
    });
  };

  const prepareDocuments = useCallback(
    async (sessionId: string, documents: ChatDocumentAttachment[]): Promise<Record<string, string>> => {
      const bindings: Record<string, string> = {};
      for (const document of documents) {
        if (!document.mediaType || !document.markdown) {
          throw new Error("文档信息不完整，请移除后重新上传");
        }
        if (document.serverDocumentId) {
          if (document.documentSessionId === sessionId) {
            bindings[document.localId] = document.serverDocumentId;
            continue;
          }
          throw new Error("文档仅属于原对话，请重新上传后再使用");
        }
        const registered = await registerParsedDocument({
          localSessionId: sessionId,
          filename: document.fileName,
          mediaType: document.mediaType,
          source: document.source,
          markdown: document.markdown,
        });
        bindings[document.localId] = registered.document_id;
      }
      return bindings;
    },
    []
  );

  const handleSend = async (
    text: string,
    images?: ImageAttachment[],
    documents: ChatDocumentAttachment[] = [],
    requestedCapabilities: string[] = [],
  ) => {
    const workflow = chatAction === "companion" ? "companion" : "standard";
    if (chatAction !== "none" && chatAction !== "companion") {
      toast.show("请先保存信息或返回健康咨询后再发送消息。");
      return false;
    }
    if (workflow === "companion" && (images?.length || documents.length)) {
      toast.show("陪伴模式不接收图片、文件或技能，请用文字或语音交流。");
      return false;
    }
    if (!currentSessionId) {
      const sid = createSession(role);
      if (workflow === "standard" && loadedSkillIds.length > 0) {
        stageSkillSelection(sid, loadedSkillIds);
      }
      setCurrentSession(sid);
      try {
        const bindings = await prepareDocuments(sid, documents);
        doSend(
          sid,
          text,
          false,
          images,
          Object.values(bindings),
          workflow,
          requestedCapabilities,
        );
        return { accepted: true as const, documentBindings: bindings, documentSessionId: sid };
      } catch (error) {
        toast.show(error instanceof Error ? error.message : "文档无法安全加入本次对话");
        return false;
      }
    }
    const liveSessionId = useAppStore.getState().currentSessionId;
    if (
      liveSessionId !== currentSessionId ||
      (workflow === "standard" && !isSkillSelectionReady(liveSessionId))
    ) {
      toast.show("正在恢复当前会话的技能，请稍候再发送");
      return false;
    }
    try {
      const bindings = await prepareDocuments(currentSessionId, documents);
      doSend(
        currentSessionId,
        text,
        false,
        images,
        Object.values(bindings),
        workflow,
        requestedCapabilities,
      );
      return {
        accepted: true as const,
        documentBindings: bindings,
        documentSessionId: currentSessionId,
      };
    } catch (error) {
      toast.show(error instanceof Error ? error.message : "文档无法安全加入本次对话");
      return false;
    }
  };

  const handleExampleClick = (text: string) => {
    handleSend(text);
  };

  const handlePrescriptionDraftGenerated = useCallback(
    (draft: FivePrescriptionDraft) => {
      const report = fivePrescriptionDraftToMarkdown(draft);
      // Opening a panel intentionally clears stale content.  Set its type
      // first, then attach this validated report and persist it with the
      // session so a clinician can return to the same draft later.
      setRightPanel("prescription");
      setPanelContent(report);
      if (currentSessionId) {
        updateSession(currentSessionId, {
          panelType: "prescription",
          panelContent: report,
        });
      }
    },
    [currentSessionId, setPanelContent, setRightPanel, updateSession]
  );

  const handleStartAction = (action: ChatActionType) => {
    if (action === "none") return;
    if (action === "health-profile") {
      setRightPanel("health-profile");
      return;
    }
    if (action === "cga") {
      setChatAction("cga");
      return;
    }
    if (action === "chronic-care") {
      setChatAction("chronic-care");
      return;
    }
    if (action === "risk-alerts") {
      setChatAction("risk-alerts");
      return;
    }
    if (action === "companion") {
      // A fresh local session prevents ordinary medical-chat context, a selected
      // Skill, or a pending document from silently crossing into this mode.
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

  /**
   * Only interruptible workflows warrant a confirmation. Read-only ledgers
   * persist each request independently, so warning about unsaved progress
   * there is both inaccurate and needlessly blocks a simple return.
   */
  const handleExitAction = () => {
    if (chatAction === "cga") {
      setExitConfirmType('cga-server');
      setShowExitConfirm(true);
      return;
    }
    if (chatAction === "drug-review") {
      setExitConfirmType('clinical-intake');
      setShowExitConfirm(true);
      return;
    }
    if (chatAction === "prescription") {
      setExitConfirmType("prescription");
      setShowExitConfirm(true);
      return;
    }
    if (chatAction === "chronic-care" || chatAction === "risk-alerts" || chatAction === "companion") {
      doExitAction();
      return;
    }
    doExitAction();
  };
  const doExitAction = () => {
    setShowExitConfirm(false);
    stopActiveAudioPlayer();
    if (chatAction === "cga") {
      setChatAction("none");
      return;
    }
    setChatAction("none");
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
        onConfirmExit={doExitAction}
      />
    </>
  );
}
