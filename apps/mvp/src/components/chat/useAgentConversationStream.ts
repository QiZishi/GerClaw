"use client";

import { useRef } from "react";

import { toast } from "@/components/ui/toast";
import { generateId } from "@/lib/format";
import {
  attachAgentRun,
  resumeAgentRun,
  streamAgentChat,
} from "@/services/gerclaw/chat";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import type { ImageAttachment, Message, MessageBlock } from "@/types";

export interface ConversationRegeneration {
  sourceRunId: string;
  expectedCurrentAnswerVersionId: string;
}

export interface ConversationResume {
  runId: string;
  publicSummaries: string[];
  mode: "attach" | "resume";
  afterSequence: number;
}

export type SendAgentTurn = (
  sessionId: string,
  text: string,
  isRegenerate?: boolean,
  images?: ImageAttachment[],
  uploadedDocumentIds?: string[],
  workflow?: "standard" | "companion",
  requestedCapabilities?: string[],
  regeneration?: ConversationRegeneration,
  replaceMessageId?: string,
  replacementSnapshot?: Message,
  resume?: ConversationResume,
) => void;

function getMessageText(message: Message): string {
  return message.blocks
    .filter(
      (block): block is Extract<MessageBlock, { kind: "text" }> =>
        block.kind === "text",
    )
    .map((block) => block.content)
    .join("\n");
}

/**
 * Owns one foreground Run stream and projects its public events into messages.
 *
 * The page supplies only the turn intent; cancellation, emergency short
 * circuiting and terminal message reconciliation remain inside this hook.
 */
export function useAgentConversationStream(): {
  sendTurn: SendAgentTurn;
  stopTurn: (sessionId: string) => void;
} {
  const loadedSkillIds = useAppStore((state) => state.loadedSkillIds);
  const addMessage = useChatStore((state) => state.addMessage);
  const updateMessage = useChatStore((state) => state.updateMessage);
  const appendMessageText = useChatStore((state) => state.appendMessageText);
  const initMessageThinking = useChatStore((state) => state.initMessageThinking);
  const appendMessageThinking = useChatStore((state) => state.appendMessageThinking);
  const finalizeMessageThinking = useChatStore((state) => state.finalizeMessageThinking);
  const initMessageToolCall = useChatStore((state) => state.initMessageToolCall);
  const completeMessageToolCall = useChatStore((state) => state.completeMessageToolCall);
  const failMessageToolCall = useChatStore((state) => state.failMessageToolCall);
  const updateSession = useChatStore((state) => state.updateSession);
  const setGenerating = useChatStore((state) => state.setGenerating);

  const abortControllersRef = useRef(new Map<string, AbortController>());

  const stopTurn = (sessionId: string) => {
    const controller = abortControllersRef.current.get(sessionId);
    if (!controller) return;
    controller.abort();
    toast.show("正在安全停止，等待服务器确认执行终态");
  };

  const sendTurn: SendAgentTurn = (
    sessionId,
    text,
    isRegenerate = false,
    images,
    uploadedDocumentIds = [],
    workflow = "standard",
    requestedCapabilities = [],
    regeneration,
    replaceMessageId,
    replacementSnapshot,
    resume,
  ) => {
    if (abortControllersRef.current.has(sessionId)) {
      toast.show("当前对话仍有回答正在生成");
      return;
    }
    const userBlocks: MessageBlock[] = [];
    for (const image of images ?? []) {
      userBlocks.push({
        kind: "image",
        id: generateId("block"),
        data: image,
      });
    }
    if (text) {
      userBlocks.push({ kind: "text", id: generateId("block"), content: text });
    }
    if (!isRegenerate) {
      addMessage({
        id: generateId("msg"),
        sessionId,
        role: "user",
        blocks: userBlocks,
        status: "done",
        createdAt: Date.now(),
        uploadedFiles:
          uploadedDocumentIds.length > 0 ? uploadedDocumentIds : undefined,
        workflow,
      });
    }
    setGenerating(sessionId, true);

    const assistantMessageId = replaceMessageId ?? generateId("msg");
    const assistantBlockId = generateId("block");
    const initialThinkingBlockId = generateId("block");
    const currentThinkingBlockId = initialThinkingBlockId;
    const assistantMessage: Message = {
      id: assistantMessageId,
      sessionId,
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
      workflow,
    };
    if (replaceMessageId) {
      updateMessage(replaceMessageId, assistantMessage);
    } else {
      addMessage(assistantMessage);
    }
    initMessageThinking(assistantMessageId, initialThinkingBlockId);
    for (const summary of resume?.publicSummaries ?? []) {
      appendMessageThinking(
        assistantMessageId,
        initialThinkingBlockId,
        `${summary}\n`,
      );
    }

    const toolCallBlockMap = new Map<string, string>();
    let thinkingFinished = false;
    let emergencyShortCircuit = false;
    const abortController = new AbortController();
    abortControllersRef.current.set(sessionId, abortController);
    const finishTurn = () => {
      if (abortControllersRef.current.get(sessionId) !== abortController) return;
      abortControllersRef.current.delete(sessionId);
      setGenerating(sessionId, false);
    };
    const streamTurn: typeof streamAgentChat = resume
      ? (_input, signal, callbacks) =>
          resume.mode === "attach"
            ? attachAgentRun(
                resume.runId,
                resume.afterSequence,
                signal,
                callbacks,
              )
            : resumeAgentRun(resume.runId, signal, callbacks)
      : streamAgentChat;

    void streamTurn(
      {
        localSessionId: sessionId,
        message: text,
        loadedSkills: workflow === "companion" ? [] : loadedSkillIds,
        uploadedDocumentIds:
          workflow === "companion" ? [] : uploadedDocumentIds,
        images: workflow === "companion" ? [] : images,
        workflow,
        requestedCapabilities:
          workflow === "companion" ? [] : requestedCapabilities,
        regeneration,
      },
      abortController.signal,
      {
        onThinking: (content) => {
          if (emergencyShortCircuit) return;
          const currentId = currentThinkingBlockId;
          if (currentId && !thinkingFinished) {
            appendMessageThinking(
              assistantMessageId,
              currentId,
              `${content}\n`,
            );
          }
        },
        onText: (delta) => {
          if (emergencyShortCircuit) return;
          const currentId = currentThinkingBlockId;
          if (currentId && !thinkingFinished) {
            finalizeMessageThinking(assistantMessageId, currentId);
            thinkingFinished = true;
          }
          appendMessageText(assistantMessageId, assistantBlockId, delta);
        },
        onToolCall: ({ id, name }) => {
          if (emergencyShortCircuit) return;
          const toolBlockId = generateId("block");
          toolCallBlockMap.set(id, toolBlockId);
          initMessageToolCall(assistantMessageId, toolBlockId, id, name);
        },
        onToolResult: ({ id, status, durationMs, results }) => {
          if (emergencyShortCircuit) return;
          const toolBlockId = toolCallBlockMap.get(id);
          if (!toolBlockId) return;
          if (status !== "success") {
            failMessageToolCall(
              assistantMessageId,
              toolBlockId,
              status === "cancelled"
                ? "用户已停止生成"
                : `工具执行失败${
                    durationMs === undefined ? "" : `（${durationMs}ms）`
                  }`,
            );
            return;
          }
          completeMessageToolCall(assistantMessageId, toolBlockId, {}, {
            status,
            duration_ms: durationMs,
            results,
          });
        },
        onApprovalRequired: (approval) => {
          if (emergencyShortCircuit) return;
          const currentId = currentThinkingBlockId;
          if (currentId && !thinkingFinished) {
            finalizeMessageThinking(assistantMessageId, currentId);
            thinkingFinished = true;
          }
          const currentMessage = useChatStore
            .getState()
            .messagesBySession[sessionId]?.find(
              (message) => message.id === assistantMessageId,
            );
          if (
            !currentMessage ||
            currentMessage.blocks.some(
              (block) =>
                block.kind === "runtime_approval" &&
                block.data.approvalId === approval.id,
            )
          ) {
            return;
          }
          updateMessage(assistantMessageId, {
            blocks: [
              ...currentMessage.blocks.map((block) =>
                block.kind === "text" && block.id === assistantBlockId
                  ? {
                      ...block,
                      content:
                        "为保护您的权益，该操作已暂停，正在等待人工授权。",
                      streaming: false,
                    }
                  : block,
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
          const currentId = currentThinkingBlockId;
          if (currentId && !thinkingFinished) {
            finalizeMessageThinking(assistantMessageId, currentId);
            thinkingFinished = true;
          }
          emergencyShortCircuit = true;
          updateMessage(assistantMessageId, {
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
        onDone: (fullText, citations, traceId, answer) => {
          const currentId = currentThinkingBlockId;
          if (currentId && !thinkingFinished) {
            finalizeMessageThinking(assistantMessageId, currentId);
          }
          const currentMessage = useChatStore
            .getState()
            .messagesBySession[sessionId]?.find(
              (message) => message.id === assistantMessageId,
            );
          const updatedBlocks = emergencyShortCircuit
            ? (currentMessage?.blocks ?? [])
            : (currentMessage?.blocks.map((block) =>
                block.kind === "text" && block.id === assistantBlockId
                  ? { ...block, content: fullText, streaming: false }
                  : block,
              ) ?? []);
          updateMessage(assistantMessageId, {
            status: "done",
            blocks: updatedBlocks,
            citations:
              emergencyShortCircuit || citations.length === 0
                ? undefined
                : citations,
            hasDisclaimer: true,
            traceId,
            executionRunId: answer?.runId,
            answerGroupRunId: answer?.answerGroupRunId,
            answerVersionId: answer?.answerVersionId,
            answerVersion: answer?.answerVersion,
            autoTtsPending:
              !emergencyShortCircuit &&
              (() => {
                const appState = useAppStore.getState();
                return (
                  appState.role === "patient" &&
                  appState.seniorMode &&
                  appState.autoTtsPlayback &&
                  appState.ttsAvailable
                );
              })(),
          });
          finishTurn();
          if (!isRegenerate) {
            const firstUserMessage = (
              useChatStore.getState().messagesBySession[sessionId] ?? []
            ).find((message) => message.role === "user");
            const session = useChatStore
              .getState()
              .sessions.find((candidate) => candidate.id === sessionId);
            if (firstUserMessage && session?.title === "新对话") {
              updateSession(sessionId, {
                title: getMessageText(firstUserMessage).slice(0, 20),
              });
            }
          }
        },
        onCancelled: (_traceId, cancellationMessage) => {
          if (replacementSnapshot) {
            updateMessage(assistantMessageId, replacementSnapshot);
            finishTurn();
            useAppStore.getState().setStreamingInterrupted(false);
            toast.show("已停止重新生成，保留原回答");
            return;
          }
          if (emergencyShortCircuit) {
            updateMessage(assistantMessageId, {
              status: "done",
              citations: undefined,
              hasDisclaimer: true,
            });
            finishTurn();
            useAppStore.getState().setStreamingInterrupted(false);
            return;
          }
          const currentId = currentThinkingBlockId;
          if (currentId && !thinkingFinished) {
            finalizeMessageThinking(assistantMessageId, currentId);
            thinkingFinished = true;
          }
          const stoppedAt = Date.now();
          const currentMessage = useChatStore
            .getState()
            .messagesBySession[sessionId]?.find(
              (message) => message.id === assistantMessageId,
            );
          const stoppedNotice =
            workflow === "companion"
              ? `⚠️ ${cancellationMessage}以上内容不完整，请重新生成或稍后再试。`
              : `⚠️ ${cancellationMessage}以上内容不完整且未通过最终校验，请勿据此调整治疗或用药。`;
          const updatedBlocks =
            currentMessage?.blocks.map((block) => {
              if (block.kind === "text" && block.id === assistantBlockId) {
                return {
                  ...block,
                  streaming: false,
                  content: block.content.trim()
                    ? `${block.content.trim()}\n\n---\n\n${stoppedNotice}`
                    : stoppedNotice,
                };
              }
              if (
                block.kind === "thinking" &&
                block.data.status === "thinking"
              ) {
                return {
                  ...block,
                  data: {
                    ...block.data,
                    status: "done" as const,
                    endedAt: stoppedAt,
                  },
                };
              }
              if (
                block.kind === "tool_call" &&
                block.data.status === "running"
              ) {
                return {
                  ...block,
                  data: {
                    ...block.data,
                    status: "failed" as const,
                    errorMessage: "用户已停止生成",
                    endedAt: stoppedAt,
                    durationMs: Math.max(
                      0,
                      stoppedAt - block.data.startedAt,
                    ),
                  },
                };
              }
              return block;
            }) ?? [];
          updateMessage(assistantMessageId, {
            status: "stopped",
            blocks: updatedBlocks,
            hasDisclaimer: true,
          });
          finishTurn();
          useAppStore.getState().setStreamingInterrupted(false);
        },
        onError: (error) => {
          if (replacementSnapshot) {
            updateMessage(assistantMessageId, replacementSnapshot);
            finishTurn();
            useAppStore.getState().setStreamingInterrupted(false);
            toast.show(error.message);
            return;
          }
          if (emergencyShortCircuit) {
            updateMessage(assistantMessageId, {
              status: "done",
              citations: undefined,
              hasDisclaimer: true,
            });
            finishTurn();
            return;
          }
          const currentId = currentThinkingBlockId;
          if (currentId && !thinkingFinished) {
            finalizeMessageThinking(assistantMessageId, currentId);
          }
          const currentMessage = useChatStore
            .getState()
            .messagesBySession[sessionId]?.find(
              (message) => message.id === assistantMessageId,
            );
          const awaitingApproval = error.code === "CHAT_APPROVAL_REQUIRED";
          const failedAt = Date.now();
          const updatedBlocks =
            currentMessage?.blocks.map((block) => {
              if (block.kind === "text" && block.id === assistantBlockId) {
                const partialContent = block.content.trim();
                const incompleteNotice =
                  workflow === "companion"
                    ? "⚠️ 本次回复未完成，未通过最终安全校验。请点击“重新生成”重试。"
                    : "⚠️ 本次回答未完成，未通过最终安全校验。请点击“重新生成”重试；请勿据此调整治疗或用药。";
                return {
                  ...block,
                  content: awaitingApproval
                    ? block.content || "该操作已安全暂停，等待人工授权。"
                    : partialContent
                      ? `${partialContent}\n\n---\n\n${incompleteNotice}`
                      : `${error.message}\n\n${incompleteNotice}`,
                  streaming: false,
                };
              }
              if (
                block.kind === "tool_call" &&
                block.data.status === "running"
              ) {
                return {
                  ...block,
                  data: {
                    ...block.data,
                    status: "failed" as const,
                    errorMessage: "响应中断，工具结果未完成",
                    endedAt: failedAt,
                    durationMs: Math.max(
                      0,
                      failedAt - block.data.startedAt,
                    ),
                  },
                };
              }
              return block;
            }) ?? [];
          updateMessage(assistantMessageId, {
            status: awaitingApproval ? "done" : "error",
            blocks: updatedBlocks,
            hasDisclaimer: true,
          });
          finishTurn();
          useAppStore.getState().setStreamingInterrupted(false);
        },
      },
    );
  };

  return { sendTurn, stopTurn };
}
