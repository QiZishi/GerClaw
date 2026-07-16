"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ArrowLeft,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { ChatInput, type ChatDocumentAttachment } from "@/components/chat/ChatInput";
import { MessageList } from "@/components/chat/MessageList";
import { ExportDialog } from "@/components/chat/ExportDialog";
import { WelcomePage } from "@/components/chat/WelcomePage";
import { SkillManager } from "@/components/skills/SkillManager";
import { CgaAssessment } from "@/components/cga/CgaAssessment";
import { ClinicalIntakeForm } from "@/components/prescription/ClinicalIntakeForm";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import { cn } from "@/lib/utils";
import { streamAgentChat } from "@/services/gerclaw/chat";
import { readSessionSkills, replaceSessionSkills } from "@/services/gerclaw/skills";
import { registerParsedDocument } from "@/services/gerclaw/documents";
import { generateId } from "@/lib/format";
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
  const currentSessionId = useAppStore((s) => s.currentSessionId);
  const setCurrentSession = useAppStore((s) => s.setCurrentSession);
  const mainView = useAppStore((s) => s.mainView);
  const setMainView = useAppStore((s) => s.setMainView);
  const chatAction = useAppStore((s) => s.chatAction);
  const setChatAction = useAppStore((s) => s.setChatAction);
  const setRightPanel = useAppStore((s) => s.setRightPanel);
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const loadedSkillIds = useAppStore((s) => s.loadedSkillIds);
  const setLoadedSkills = useAppStore((s) => s.setLoadedSkills);
  const isGenerating = useChatStore((s) => s.isGenerating);
  const setGenerating = useChatStore((s) => s.setGenerating);

  const messagesBySession = useChatStore((s) => s.messagesBySession);
  const addMessage = useChatStore((s) => s.addMessage);
  const updateMessage = useChatStore((s) => s.updateMessage);
  const appendMessageText = useChatStore((s) => s.appendMessageText);
  const initMessageThinking = useChatStore((s) => s.initMessageThinking);
  const appendMessageThinking = useChatStore((s) => s.appendMessageThinking);
  const finalizeMessageThinking = useChatStore((s) => s.finalizeMessageThinking);
  const initMessageToolCall = useChatStore((s) => s.initMessageToolCall);
  const completeMessageToolCall = useChatStore((s) => s.completeMessageToolCall);
  const failMessageToolCall = useChatStore((s) => s.failMessageToolCall);
  const removeMessage = useChatStore((s) => s.removeMessage);
  const deleteMessage = useChatStore((s) => s.deleteMessage);
  const updateSession = useChatStore((s) => s.updateSession);
  const createSession = useChatStore((s) => s.createSession);
  const storeSessions = useChatStore((s) => s.sessions);

  const abortControllerRef = useRef<AbortController | null>(null);
  const currentThinkingBlockIdRef = useRef<string | null>(null);
  const skillSelectionLoadRef = useRef(0);
  const pendingSkillSelectionRef = useRef(new Map<string, string[]>());
  const [skillSelectionReadySessionId, setSkillSelectionReadySessionId] = useState<string | null>(null);
  const skillSelectionReadySessionIdRef = useRef<string | null>(null);

  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
  }, []);

  // 老年模式退出功能二次确认弹窗
  const [showExitConfirm, setShowExitConfirm] = useState(false);
  const [exitConfirmType, setExitConfirmType] = useState<'default' | 'cga-in-progress' | 'cga-has-result' | 'cga-server' | 'clinical-intake'>('default');
  // 消息导出/分享弹窗：值为触发的消息 id（用于默认选中），null 表示关闭
  const [exportMessageId, setExportMessageId] = useState<string | null>(null);
  // 消息删除确认弹窗：值为待删除的消息 id，null 表示关闭
  const [deleteMessageId, setDeleteMessageId] = useState<string | null>(null);



  const messages: Message[] = currentSessionId
    ? messagesBySession[currentSessionId] ?? []
    : [];

  const currentSessionTitle = (() => {
    if (!currentSessionId) return "";
    const fromStore = storeSessions.find((s) => s.id === currentSessionId);
    return fromStore?.title ?? "";
  })();

  /** 从消息中提取纯文本内容 */
  const getTextFromMessage = (msg: Message): string => {
    return msg.blocks
      .filter((b): b is Extract<MessageBlock, { kind: "text" }> => b.kind === "text")
      .map((b) => b.content)
      .join("\n");
  };

  useEffect(() => {
    if (!currentSessionId) {
      skillSelectionLoadRef.current += 1;
      setLoadedSkills([]);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSkillSelectionReadySessionId(null);
      skillSelectionReadySessionIdRef.current = null;
      return;
    }
    const loadId = ++skillSelectionLoadRef.current;
    // Never expose the previous conversation's Skills while the new
    // conversation selection is being restored from the backend.
    setLoadedSkills([]);
    setSkillSelectionReadySessionId(null);
    skillSelectionReadySessionIdRef.current = null;
    const pendingSelection = pendingSkillSelectionRef.current.get(currentSessionId);
    pendingSkillSelectionRef.current.delete(currentSessionId);
    const loadSelection = pendingSelection
      ? replaceSessionSkills(currentSessionId, pendingSelection)
      : readSessionSkills(currentSessionId);
    void loadSelection
      .then((skillIds) => {
        if (
          loadId === skillSelectionLoadRef.current &&
          useAppStore.getState().currentSessionId === currentSessionId
        ) {
          setLoadedSkills(skillIds);
          skillSelectionReadySessionIdRef.current = currentSessionId;
          setSkillSelectionReadySessionId(currentSessionId);
        }
      })
      .catch((error) => {
        if (
          loadId === skillSelectionLoadRef.current &&
          useAppStore.getState().currentSessionId === currentSessionId
        ) {
          setLoadedSkills([]);
          skillSelectionReadySessionIdRef.current = currentSessionId;
          setSkillSelectionReadySessionId(currentSessionId);
          toast.show(error instanceof Error ? error.message : "会话技能未能恢复");
        }
      });
  }, [currentSessionId, setLoadedSkills]);

  // 仅健康画像由右侧面板承载；其余入口均由各自的真实后端流程承载。
  useEffect(() => {
    if (chatAction === "none" || chatAction === "cga" || chatAction === "prescription" || chatAction === "drug-review") return;
    setChatAction("none");
  }, [chatAction, setChatAction]);

  /** 首次AI回复完成后自动设置会话标题 */
  const trySetSessionTitle = (sid: string, firstUserText: string) => {
    const session = storeSessions.find((s) => s.id === sid);
    if (session && session.title === "新对话") {
      const title = firstUserText.slice(0, 20);
      updateSession(sid, { title });
    }
  };

  /** 停止生成 */
  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      toast.show("正在安全停止，等待服务器确认执行终态");
    }
  };

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
    const userText = getTextFromMessage(userMsg);
    const userImages: ImageAttachment[] = userMsg.blocks
      .filter((b): b is Extract<MessageBlock, { kind: "image" }> => b.kind === "image")
      .map((b) => b.data);
    
    const messagesToRemove = messages.slice(userMsgIndex + 1, aiMsgIndex + 1);
    messagesToRemove.forEach((m) => removeMessage(m.id));
    
    doSend(currentSessionId, userText, true, userImages.length > 0 ? userImages : undefined);
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
    documents: ChatDocumentAttachment[] = []
  ) => {
    if (chatAction !== "none") {
      toast.show("请先保存信息或返回健康咨询后再发送消息。");
      return false;
    }
    if (!currentSessionId) {
      const sid = createSession(role);
      if (loadedSkillIds.length > 0) {
        pendingSkillSelectionRef.current.set(sid, [...loadedSkillIds]);
      }
      setCurrentSession(sid);
      try {
        const bindings = await prepareDocuments(sid, documents);
        doSend(sid, text, false, images, Object.values(bindings));
        return { accepted: true as const, documentBindings: bindings, documentSessionId: sid };
      } catch (error) {
        toast.show(error instanceof Error ? error.message : "文档无法安全加入本次对话");
        return false;
      }
    }
    const liveSessionId = useAppStore.getState().currentSessionId;
    if (
      liveSessionId !== currentSessionId ||
      skillSelectionReadySessionIdRef.current !== liveSessionId
    ) {
      toast.show("正在恢复当前会话的技能，请稍候再发送");
      return false;
    }
    try {
      const bindings = await prepareDocuments(currentSessionId, documents);
      doSend(currentSessionId, text, false, images, Object.values(bindings));
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

  const doSend = (
    sid: string,
    text: string,
    isRegenerate = false,
    images?: ImageAttachment[],
    uploadedDocumentIds: string[] = []
  ) => {
    const userBlocks: MessageBlock[] = [];
    if (images && images.length > 0) {
      for (const img of images) {
        userBlocks.push({
          kind: "image",
          id: generateId("block"),
          data: img,
        });
      }
    }
    if (text) {
      userBlocks.push({ kind: "text", id: generateId("block"), content: text });
    }
    const userMsg: Message = {
      id: generateId("msg"),
      sessionId: sid,
      role: "user",
      blocks: userBlocks,
      status: "done",
      createdAt: Date.now(),
    };
    if (!isRegenerate) {
      addMessage(userMsg);
    }
    setGenerating(true);

    const assistantMsgId = generateId("msg");
    const assistantBlockId = generateId("block");
    const initialThinkingBlockId = generateId("block");
    currentThinkingBlockIdRef.current = initialThinkingBlockId;

    const assistantMsg: Message = {
      id: assistantMsgId,
      sessionId: sid,
      role: "assistant",
      blocks: [
        {
          kind: "text",
          id: assistantBlockId,
          content: "",
          streaming: true,
        },
      ],
      status: "streaming",
      createdAt: Date.now(),
      hasDisclaimer: false,
    };
    addMessage(assistantMsg);
    initMessageThinking(assistantMsgId, initialThinkingBlockId);

    const toolCallBlockMap = new Map<string, string>();
    let thinkingFinished = false;
    let emergencyShortCircuit = false;
    abortControllerRef.current = new AbortController();

    void streamAgentChat(
      {
        localSessionId: sid,
        message: text,
        loadedSkills: loadedSkillIds,
        uploadedDocumentIds,
      },
      abortControllerRef.current.signal,
      {
        onThinking: (content) => {
          if (emergencyShortCircuit) return;
          const currentId = currentThinkingBlockIdRef.current;
          if (currentId && !thinkingFinished) {
            appendMessageThinking(assistantMsgId, currentId, `${content}\n`);
          }
        },
        onText: (delta) => {
          if (emergencyShortCircuit) return;
          const currentId = currentThinkingBlockIdRef.current;
          if (currentId && !thinkingFinished) {
            finalizeMessageThinking(assistantMsgId, currentId);
            thinkingFinished = true;
          }
          appendMessageText(assistantMsgId, assistantBlockId, delta);
        },
        onToolCall: ({ id, name }) => {
          if (emergencyShortCircuit) return;
          const toolBlockId = generateId("block");
          toolCallBlockMap.set(id, toolBlockId);
          initMessageToolCall(assistantMsgId, toolBlockId, id, name);
        },
        onToolResult: ({ id, status, durationMs, results }) => {
          if (emergencyShortCircuit) return;
          const toolBlockId = toolCallBlockMap.get(id);
          if (!toolBlockId) return;
          if (status !== "success") {
            failMessageToolCall(
              assistantMsgId,
              toolBlockId,
              status === "cancelled"
                ? "用户已停止生成"
                : `工具执行失败${durationMs === undefined ? "" : `（${durationMs}ms）`}`
            );
            return;
          }
          completeMessageToolCall(assistantMsgId, toolBlockId, {}, {
            status,
            duration_ms: durationMs,
            results,
          });
        },
        onApprovalRequired: (approval) => {
          if (emergencyShortCircuit) return;
          const currentId = currentThinkingBlockIdRef.current;
          if (currentId && !thinkingFinished) {
            finalizeMessageThinking(assistantMsgId, currentId);
            thinkingFinished = true;
          }
          const msgNow = useChatStore.getState().messagesBySession[sid]?.find(
            (message) => message.id === assistantMsgId
          );
          if (!msgNow || msgNow.blocks.some((block) => block.kind === "runtime_approval" && block.data.approvalId === approval.id)) return;
          updateMessage(assistantMsgId, {
            blocks: [
              ...msgNow.blocks.map((block) =>
                block.kind === "text" && block.id === assistantBlockId
                  ? { ...block, content: "为保护您的权益，该操作已暂停，正在等待人工授权。", streaming: false }
                  : block
              ),
              {
                kind: "runtime_approval",
                id: generateId("block"),
                data: {
                  approvalId: approval.id,
                  toolName: approval.toolName,
                  expiresAt: approval.expiresAt,
                  policyVersion: approval.policyVersion,
                  toolVersion: approval.toolVersion,
                },
              },
            ],
            status: "done",
            hasDisclaimer: true,
          });
        },
        onSafetyNotice: ({ codes, content }) => {
          const currentId = currentThinkingBlockIdRef.current;
          if (currentId && !thinkingFinished) {
            finalizeMessageThinking(assistantMsgId, currentId);
            thinkingFinished = true;
          }
          emergencyShortCircuit = true;
          updateMessage(assistantMsgId, {
            blocks: [
              {
                kind: "emergency_alert",
                id: generateId("block"),
                data: { codes, message: content },
              },
            ],
            status: "streaming",
            hasDisclaimer: true,
          });
        },
        onDone: (fullText, citations, traceId) => {
          abortControllerRef.current = null;
          const currentId = currentThinkingBlockIdRef.current;
          if (currentId && !thinkingFinished) finalizeMessageThinking(assistantMsgId, currentId);
          const msgNow = useChatStore.getState().messagesBySession[sid]?.find((message) => message.id === assistantMsgId);
          const updatedBlocks = emergencyShortCircuit
            ? (msgNow?.blocks ?? [])
            : msgNow?.blocks.map((block) =>
                block.kind === "text" && block.id === assistantBlockId
                  ? { ...block, content: fullText, streaming: false }
                  : block
              ) ?? [];
          updateMessage(assistantMsgId, {
            status: "done",
            blocks: updatedBlocks,
            citations: emergencyShortCircuit || citations.length === 0 ? undefined : citations,
            hasDisclaimer: true,
            traceId,
          });
          setGenerating(false);
          if (!isRegenerate) {
            const firstUserMsg = (useChatStore.getState().messagesBySession[sid] ?? []).find((message) => message.role === "user");
            if (firstUserMsg) trySetSessionTitle(sid, getTextFromMessage(firstUserMsg));
          }
        },
        onCancelled: (_traceId, cancellationMessage) => {
          abortControllerRef.current = null;
          if (emergencyShortCircuit) {
            updateMessage(assistantMsgId, {
              status: "done",
              citations: undefined,
              hasDisclaimer: true,
            });
            setGenerating(false);
            useAppStore.getState().setStreamingInterrupted(false);
            return;
          }
          const currentId = currentThinkingBlockIdRef.current;
          if (currentId && !thinkingFinished) {
            finalizeMessageThinking(assistantMsgId, currentId);
            thinkingFinished = true;
          }
          const stoppedAt = Date.now();
          const msgNow = useChatStore.getState().messagesBySession[sid]?.find(
            (message) => message.id === assistantMsgId
          );
          const stoppedNotice = `⚠️ ${cancellationMessage}以上内容不完整且未通过最终校验，请勿据此调整治疗或用药。`;
          const updatedBlocks = msgNow?.blocks.map((block) => {
            if (block.kind === "text" && block.id === assistantBlockId) {
              return {
                ...block,
                streaming: false,
                content: block.content.trim()
                  ? `${block.content.trim()}\n\n---\n\n${stoppedNotice}`
                  : stoppedNotice,
              };
            }
            if (block.kind === "thinking" && block.data.status === "thinking") {
              return {
                ...block,
                data: { ...block.data, status: "done" as const, endedAt: stoppedAt },
              };
            }
            if (block.kind === "tool_call" && block.data.status === "running") {
              return {
                ...block,
                data: {
                  ...block.data,
                  status: "failed" as const,
                  errorMessage: "用户已停止生成",
                  endedAt: stoppedAt,
                  durationMs: Math.max(0, stoppedAt - block.data.startedAt),
                },
              };
            }
            return block;
          }) ?? [];
          updateMessage(assistantMsgId, {
            status: "stopped",
            blocks: updatedBlocks,
            hasDisclaimer: true,
          });
          setGenerating(false);
          useAppStore.getState().setStreamingInterrupted(false);
        },
        onError: (error) => {
          abortControllerRef.current = null;
          if (emergencyShortCircuit) {
            updateMessage(assistantMsgId, {
              status: "done",
              citations: undefined,
              hasDisclaimer: true,
            });
            setGenerating(false);
            return;
          }
          const currentId = currentThinkingBlockIdRef.current;
          if (currentId && !thinkingFinished) finalizeMessageThinking(assistantMsgId, currentId);
          const msgNow = useChatStore.getState().messagesBySession[sid]?.find((message) => message.id === assistantMsgId);
          const awaitingApproval = error.code === "CHAT_APPROVAL_REQUIRED";
          const failedAt = Date.now();
          const updatedBlocks = msgNow?.blocks.map((block) => {
            if (block.kind === "text" && block.id === assistantBlockId) {
              const partialContent = block.content.trim();
              const incompleteNotice = "⚠️ 本次回答未完成，未通过最终安全校验。请点击“重新生成”重试；请勿据此调整治疗或用药。";
              return {
                ...block,
                content: awaitingApproval
                  ? block.content || "该操作已安全暂停，等待人工授权。"
                  : partialContent
                    ? `${partialContent}\n\n---\n\n${incompleteNotice}`
                    : `系统暂时未能完成本次回答，请稍后重试。\n\n${incompleteNotice}`,
                streaming: false,
              };
            }
            if (block.kind === "tool_call" && block.data.status === "running") {
              return {
                ...block,
                data: {
                  ...block.data,
                  status: "failed" as const,
                  errorMessage: "响应中断，工具结果未完成",
                  endedAt: failedAt,
                  durationMs: Math.max(0, failedAt - block.data.startedAt),
                },
              };
            }
            return block;
          }) ?? [];
          updateMessage(assistantMsgId, {
            status: awaitingApproval ? "done" : "error",
            blocks: updatedBlocks,
            hasDisclaimer: true,
          });
          setGenerating(false);
          useAppStore.getState().setStreamingInterrupted(false);
        },
      }
    );
};

const handleExampleClick = (text: string) => {
    handleSend(text);
  };

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
    if (action === "prescription" || action === "drug-review") {
      let sessionId = currentSessionId;
      if (!sessionId) {
        sessionId = createSession(role);
        setCurrentSession(sessionId);
      }
      setChatAction(action);
    }
  };

  /** 退出当前功能模式，清理相关状态（所有模式下二次确认）*/
  const handleExitAction = () => {
    if (chatAction === "cga") {
      setExitConfirmType('cga-server');
      setShowExitConfirm(true);
      return;
    }
    if (chatAction === "prescription" || chatAction === "drug-review") {
      setExitConfirmType('clinical-intake');
      setShowExitConfirm(true);
      return;
    }
    if (chatAction !== "none") {
      setExitConfirmType('default');
      setShowExitConfirm(true);
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

  const actionTitles: Record<string, string> = {
    prescription: "五大处方信息收集",
    cga: "老年综合评估",
    "drug-review": "用药信息收集",
    "health-profile": "查看健康画像",
  };

  if (!mounted) {
    return (
      <main className="flex-1 flex flex-col min-w-0 min-h-0 bg-background">
        <WelcomePage
          onExampleClick={() => {}}
          onStartAction={() => {}}
          role="visitor"
          seniorMode={false}
        />
      </main>
    );
  }

  if (mainView === "skills") {
    return (
      <main className="flex-1 flex flex-col min-w-0 min-h-0 bg-background">
        <header
          className={cn(
            "sticky top-0 z-10 flex min-h-12 items-center gap-2 border-b border-border bg-background/95 px-3 backdrop-blur",
            seniorMode && "py-2"
          )}
          style={sidebarCollapsed ? { paddingLeft: "112px" } : undefined}
        >
          <Button
            variant="ghost"
            size={seniorMode ? "default" : "icon-sm"}
            className={cn(
              "btn-icon shrink-0",
              seniorMode && "h-12 min-w-32 gap-2 px-4 text-lg"
            )}
            onClick={() => setMainView("chat")}
            aria-label="返回对话"
          >
            <ArrowLeft className={cn("size-4", seniorMode && "size-5")} />
            {seniorMode && <span>返回对话</span>}
          </Button>
          <span className={cn("font-medium", seniorMode && "text-lg")}>技能管理</span>
        </header>
        <div className="flex-1 min-h-0">
          <SkillManager />
        </div>
      </main>
    );
  }

  return (
    <main className="flex-1 flex flex-col min-w-0 min-h-0 bg-background">
      {/* 粘性头部 — 功能模式下始终显示功能标题栏 */}
      {(chatAction !== "cga" && (chatAction !== "none" || (currentSessionId && messages.length > 0))) && (
        <header
          className={cn(
            "sticky top-0 z-10 flex h-12 items-center px-4 border-b border-border bg-background/95 backdrop-blur",
            chatAction !== "none" ? "justify-end sm:justify-between" : "justify-between"
          )}
          style={sidebarCollapsed ? { paddingLeft: "112px" } : undefined}
        >
          {chatAction !== "none" ? (
            <>
              <span className="hidden font-medium sm:block">
                {actionTitles[chatAction]}
              </span>
              <Button
                variant="ghost"
                onClick={handleExitAction}
                className={cn("min-h-10 px-3 text-sm text-muted-foreground hover:text-foreground", seniorMode && "min-h-12 text-lg")}
              >
                退出
              </Button>
            </>
          ) : (
            <>
              <span
                className="font-medium truncate"
                title={currentSessionTitle}
              >
                {currentSessionTitle || "新对话"}
              </span>
            </>
          )}
        </header>
      )}

      {messages.length === 0 && chatAction === "none" ? (
        <WelcomePage
          onExampleClick={handleExampleClick}
          onStartAction={handleStartAction}
          role={role}
          seniorMode={seniorMode}
        />
      ) : chatAction === "cga" ? (
        <div className="flex-1 min-h-0 overflow-y-auto">
          <CgaAssessment onExit={handleExitAction} />
        </div>
      ) : chatAction === "prescription" || chatAction === "drug-review" ? (
        currentSessionId ? (
          <ClinicalIntakeForm
            localSessionId={currentSessionId}
            kind={chatAction === "prescription" ? "prescription" : "medication_review"}
            seniorMode={seniorMode}
            onExit={handleExitAction}
          />
        ) : null
      ) : (
        <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
          {messages.length > 0 && <MessageList messages={messages} onRegenerate={handleRegenerate} onShare={(messageId) => setExportMessageId(messageId)} onDelete={handleDeleteRequest} />}
        </div>
      )}

      {chatAction === "none" && (
        <ChatInput
          onSend={handleSend}
          isGenerating={isGenerating}
          onStop={handleStop}
          onStartAction={handleStartAction}
          contextLoading={Boolean(
            currentSessionId && skillSelectionReadySessionId !== currentSessionId
          )}
        />
      )}

      {/* 消息分享/导出弹窗 */}
      <ExportDialog
        open={exportMessageId !== null}
        onOpenChange={(open) => { if (!open) setExportMessageId(null); }}
        messages={messages}
        defaultSelectedIds={exportMessageId ? [exportMessageId] : []}
      />

      {/* 老年模式：退出功能二次确认弹窗 */}
      <Dialog open={showExitConfirm} onOpenChange={setShowExitConfirm}>
        <DialogContent className={cn("max-w-sm", seniorMode && "p-5")} showCloseButton={false}>
          <DialogHeader>
            <DialogTitle className={cn("flex items-center gap-2", seniorMode && "text-2xl")}>
              <AlertTriangle className="size-5 text-amber-500" />
              {exitConfirmType === "cga-server" ? "确认暂时休息？" : exitConfirmType === "clinical-intake" ? "确认返回咨询？" : "确认退出？"}
            </DialogTitle>
          </DialogHeader>
          <p className={cn("text-muted-foreground", seniorMode ? "text-lg leading-8" : "text-sm")}>
            {exitConfirmType === 'cga-has-result'
              ? "您已完成量表评估，退出后评估结果将丢失，确认退出吗？"
              : exitConfirmType === 'cga-in-progress'
                ? "退出后当前答题进度将不会保存，确认退出吗？"
                : exitConfirmType === 'cga-server'
                  ? "当前进度已安全保存。退出后，您下次可以从这道题继续。"
                  : exitConfirmType === 'clinical-intake'
                    ? "已经保存的信息会保留在当前会话；尚未点击“保存信息”的新增内容不会保留。"
                : "退出后当前进度将不会保存，确定要退出吗？"}
          </p>
          <DialogFooter className={cn("gap-2", seniorMode && "flex-row justify-end gap-3 p-5")}>
            <DialogClose render={<Button variant="outline" className={cn(seniorMode && "min-h-12 px-4 text-lg")}>取消</Button>} />
            <Button variant="destructive" className={cn(seniorMode && "min-h-12 px-4 text-lg")} onClick={doExitAction}>
              {exitConfirmType === "cga-server" ? "保存并休息" : exitConfirmType === "clinical-intake" ? "返回咨询" : "确认退出"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 消息删除确认弹窗 */}
      <Dialog open={deleteMessageId !== null} onOpenChange={(open) => { if (!open) handleDeleteCancel(); }}>
        <DialogContent className={cn("max-w-sm", seniorMode && "p-5")} showCloseButton={false}>
          <DialogHeader>
            <DialogTitle className={cn("flex items-center gap-2", seniorMode && "text-2xl")}>
              <AlertTriangle className="size-5 text-amber-500" />
              确认删除消息
            </DialogTitle>
          </DialogHeader>
          <p className={cn("text-muted-foreground", seniorMode ? "text-lg leading-8" : "text-sm")}>
            删除后该条消息将无法恢复。
          </p>
          <DialogFooter className={cn("gap-2", seniorMode && "flex-row justify-end gap-3 p-5")}>
            <DialogClose render={<Button variant="outline" className={cn(seniorMode && "min-h-12 px-4 text-lg")}>取消</Button>} />
            <Button variant="destructive" className={cn(seniorMode && "min-h-12 px-4 text-lg")} onClick={handleDeleteConfirm}>
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
