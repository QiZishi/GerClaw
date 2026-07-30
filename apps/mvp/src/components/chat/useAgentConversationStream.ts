"use client";

import { useRef } from "react";

import { toast } from "@/components/ui/toast";
import { generateId } from "@/lib/format";
import {
  type AgentChatCallbacks,
  attachAgentRun,
  queueAgentDirective,
  resumeAgentRun,
  steerAgentChat,
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

interface ActiveConversationTurn {
  controller: AbortController;
  handoffController?: AbortController;
  traceId?: string;
  assistantMessageId: string;
  finish: () => void;
  callbacks: AgentChatCallbacks;
  prepareSuccessorProjection: (instruction: string) => void;
  suppressedInterrupts: Set<string>;
  directiveInFlight: boolean;
  queueRequest?: { instruction: string; idempotencyKey: string };
  steerRequest?: { instruction: string; idempotencyKey: string };
}

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
  queueTurn: (sessionId: string, instruction: string) => Promise<boolean>;
  steerTurn: (sessionId: string, instruction: string) => Promise<boolean>;
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
  const deleteMessage = useChatStore((state) => state.deleteMessage);

  const activeTurnsRef = useRef(new Map<string, ActiveConversationTurn>());

  const stopTurn = (sessionId: string) => {
    const active = activeTurnsRef.current.get(sessionId);
    if (!active) return;
    active.controller.abort();
    active.handoffController?.abort();
    toast.show("正在停止");
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
    if (activeTurnsRef.current.has(sessionId)) {
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
    let currentThinkingBlockId = initialThinkingBlockId;
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
    const activeTurn: ActiveConversationTurn = {
      controller: abortController,
      assistantMessageId,
      finish: () => {},
      callbacks: {},
      prepareSuccessorProjection: () => {},
      suppressedInterrupts: new Set<string>(),
      directiveInFlight: false,
    };
    activeTurnsRef.current.set(sessionId, activeTurn);
    const finishTurn = () => {
      if (activeTurnsRef.current.get(sessionId) !== activeTurn) return;
      activeTurnsRef.current.delete(sessionId);
      setGenerating(sessionId, false);
    };
    activeTurn.finish = finishTurn;
    const prepareSuccessorProjection = (instruction: string) => {
      deleteMessage(assistantMessageId);
      addMessage({
        id: generateId("msg"),
        sessionId,
        role: "user",
        blocks: [
          {
            kind: "text",
            id: generateId("block"),
            content: instruction,
          },
        ],
        status: "done",
        createdAt: Date.now(),
        workflow,
      });
      currentThinkingBlockId = generateId("block");
      toolCallBlockMap.clear();
      thinkingFinished = false;
      emergencyShortCircuit = false;
      addMessage({
        ...assistantMessage,
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
      });
      initMessageThinking(assistantMessageId, currentThinkingBlockId);
    };
    activeTurn.prepareSuccessorProjection = prepareSuccessorProjection;
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

    const callbacks: AgentChatCallbacks = {
        onStarted: (traceId) => {
          if (activeTurnsRef.current.get(sessionId) === activeTurn) {
            activeTurn.traceId = traceId;
          }
        },
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
          deleteMessage(assistantMessageId);
          finishTurn();
          useAppStore.getState().setStreamingInterrupted(false);
          toast.show(cancellationMessage || "已停止生成");
        },
        onInterrupted: (traceId) => {
          if (activeTurn.suppressedInterrupts.delete(traceId)) return;
          deleteMessage(assistantMessageId);
          finishTurn();
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
          const awaitingApproval = error.code === "CHAT_APPROVAL_REQUIRED";
          if (awaitingApproval) {
            updateMessage(assistantMessageId, {
              status: "done",
              blocks: [
                {
                  kind: "text",
                  id: assistantBlockId,
                  content: "该操作等待人工授权。",
                  streaming: false,
                },
              ],
            });
          } else {
            deleteMessage(assistantMessageId);
            toast.show(error.message);
          }
          finishTurn();
          useAppStore.getState().setStreamingInterrupted(false);
        },
      };
    activeTurn.callbacks = callbacks;

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
      callbacks,
    );
  };

  const queueTurn = async (
    sessionId: string,
    instruction: string,
  ): Promise<boolean> => {
    const active = activeTurnsRef.current.get(sessionId);
    const normalized = instruction.trim();
    if (!active?.traceId || !normalized || active.directiveInFlight) return false;
    active.directiveInFlight = true;
    const request =
      active.queueRequest?.instruction === normalized
        ? active.queueRequest
        : {
            instruction: normalized,
            idempotencyKey: `directive_${crypto.randomUUID().replaceAll("-", "")}`,
          };
    active.queueRequest = request;
    try {
      await queueAgentDirective(
        active.traceId,
        request.instruction,
        request.idempotencyKey,
      );
      addMessage({
        id: generateId("msg"),
        sessionId,
        role: "user",
        blocks: [
          {
            kind: "text",
            id: generateId("block"),
            content: normalized,
          },
        ],
        status: "done",
        createdAt: Date.now(),
      });
      active.queueRequest = undefined;
      toast.show("已排队，将在下一步继续处理");
      return true;
    } catch (error) {
      toast.show(error instanceof Error ? error.message : "新要求暂时无法排队");
      return false;
    } finally {
      active.directiveInFlight = false;
    }
  };

  const steerTurn = (
    sessionId: string,
    instruction: string,
  ): Promise<boolean> => {
    const active = activeTurnsRef.current.get(sessionId);
    const normalized = instruction.trim();
    if (!active?.traceId || !normalized || active.directiveInFlight) {
      return Promise.resolve(false);
    }
    active.directiveInFlight = true;
    const sourceTraceId = active.traceId;
    const previousController = active.controller;
    const request =
      active.steerRequest?.instruction === normalized
        ? active.steerRequest
        : {
            instruction: normalized,
            idempotencyKey: `directive_${crypto.randomUUID().replaceAll("-", "")}`,
          };
    active.steerRequest = request;
    active.suppressedInterrupts.add(sourceTraceId);
    const successorController = new AbortController();
    active.handoffController = successorController;

    return new Promise<boolean>((resolve) => {
      let accepted = false;
      const baseCallbacks = active.callbacks;
      const callbacks: AgentChatCallbacks = {
        ...baseCallbacks,
        onStarted: (traceId) => {
          if (
            activeTurnsRef.current.get(sessionId) !== active ||
            previousController.signal.aborted ||
            successorController.signal.aborted
          ) {
            successorController.abort();
            active.directiveInFlight = false;
            active.steerRequest = undefined;
            active.handoffController = undefined;
            resolve(false);
            return;
          }
          accepted = true;
          active.controller = successorController;
          active.handoffController = undefined;
          active.directiveInFlight = false;
          active.steerRequest = undefined;
          active.prepareSuccessorProjection(normalized);
          baseCallbacks.onStarted?.(traceId);
          resolve(true);
        },
        onCancelled: (traceId, message) => {
          active.directiveInFlight = false;
          active.steerRequest = undefined;
          active.handoffController = undefined;
          baseCallbacks.onCancelled?.(traceId, message);
          resolve(false);
        },
        onError: (error) => {
          if (!accepted) {
            active.directiveInFlight = false;
            active.steerRequest = undefined;
            active.handoffController = undefined;
            active.suppressedInterrupts.delete(sourceTraceId);
            previousController.abort();
            if (activeTurnsRef.current.get(sessionId) === active) {
              deleteMessage(active.assistantMessageId);
              active.finish();
            }
            toast.show(error.message);
            resolve(false);
            return;
          }
          baseCallbacks.onError?.(error);
        },
      };
      void steerAgentChat(
        sourceTraceId,
        request.instruction,
        request.idempotencyKey,
        successorController.signal,
        callbacks,
      );
    });
  };

  return { sendTurn, stopTurn, queueTurn, steerTurn };
}
