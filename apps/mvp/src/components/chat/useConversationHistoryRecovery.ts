"use client";

import { useEffect, useEffectEvent, useRef } from "react";

import type { SendAgentTurn } from "@/components/chat/useAgentConversationStream";
import { toast } from "@/components/ui/toast";
import { canHydrateConversationHistory } from "@/services/gerclaw/conversation-hydration-policy";
import { planConversationRecovery } from "@/services/gerclaw/conversation-recovery";
import {
  readConversationMessages,
  toFrontendMessages,
} from "@/services/gerclaw/conversation-history";
import {
  readAgentRun,
  readRecoverableRun,
  replayAgentRunEvents,
} from "@/services/gerclaw/runs";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import type { Message, MessageBlock } from "@/types";

interface ConversationHistoryRecoveryOptions {
  currentSessionId: string | null;
  isGuest: boolean;
  contextReadySessionId: string | null;
  sendTurn: SendAgentTurn;
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
 * Hydrates only an empty owner-scoped conversation, then attaches to or
 * resumes its newest recoverable Run without replaying private reasoning.
 */
export function useConversationHistoryRecovery({
  currentSessionId,
  isGuest,
  contextReadySessionId,
  sendTurn,
}: ConversationHistoryRecoveryOptions): void {
  const setMessages = useChatStore((state) => state.setMessages);
  const loadedSessionIdsRef = useRef(new Set<string>());
  const checkedRecoverySessionIdsRef = useRef(new Set<string>());

  const resumeInterruptedRun = useEffectEvent(
    async (sessionId: string, restoredMessages: Message[]) => {
      if (checkedRecoverySessionIdsRef.current.has(sessionId)) return;
      checkedRecoverySessionIdsRef.current.add(sessionId);
      try {
        const recoverable = await readRecoverableRun(sessionId);
        const run = recoverable.run;
        if (!run) return;
        const replay =
          run.status === "interrupted"
            ? await replayAgentRunEvents(run.id, 0, 200)
            : undefined;
        const currentRun =
          run.status === "interrupted" ? await readAgentRun(run.id) : run;
        if (
          useAppStore.getState().currentSessionId !== sessionId ||
          useChatStore.getState().isGenerating
        ) {
          return;
        }
        const sourceMessage = restoredMessages.find(
          (message) => message.id === run.input_message_id,
        );
        if (!sourceMessage || sourceMessage.role !== "user") {
          toast.show("中断的回答缺少原始提问，未自动恢复");
          return;
        }
        const recovery = planConversationRecovery(currentRun, replay);
        if (recovery.action === "refresh-history") {
          const currentMessages = toFrontendMessages(
            await readConversationMessages(sessionId),
          );
          if (
            useAppStore.getState().currentSessionId === sessionId &&
            !useChatStore.getState().isGenerating
          ) {
            setMessages(sessionId, currentMessages);
          }
          return;
        }
        toast.show("正在恢复上次中断的回答");
        sendTurn(
          sessionId,
          getMessageText(sourceMessage),
          true,
          undefined,
          [],
          sourceMessage.workflow ?? "standard",
          [],
          undefined,
          undefined,
          undefined,
          {
            runId: run.id,
            publicSummaries: recovery.publicSummaries,
            mode: recovery.mode,
            afterSequence: recovery.afterSequence,
          },
        );
      } catch (error) {
        toast.show(
          error instanceof Error ? error.message : "中断的回答暂时无法恢复",
        );
      }
    },
  );

  useEffect(() => {
    if (
      isGuest ||
      !currentSessionId ||
      contextReadySessionId !== currentSessionId ||
      loadedSessionIdsRef.current.has(currentSessionId)
    ) {
      return;
    }
    let live = true;
    const sessionId = currentSessionId;
    void readConversationMessages(sessionId)
      .then((response) => {
        if (!live) return;
        loadedSessionIdsRef.current.add(sessionId);
        const localMessages = useChatStore.getState().getMessages(sessionId);
        if (!canHydrateConversationHistory(localMessages.length)) return;
        const restoredMessages = toFrontendMessages(response);
        setMessages(sessionId, restoredMessages);
        void resumeInterruptedRun(sessionId, restoredMessages);
      })
      .catch(() => {
        if (!live) return;
        loadedSessionIdsRef.current.add(sessionId);
        const localMessages = useChatStore.getState().getMessages(sessionId);
        if (!canHydrateConversationHistory(localMessages.length)) return;
        setMessages(sessionId, []);
      });
    return () => {
      live = false;
    };
  }, [currentSessionId, contextReadySessionId, isGuest, setMessages]);
}
