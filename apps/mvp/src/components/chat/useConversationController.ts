"use client";

import { useCallback } from "react";

import type { ChatDocumentAttachment } from "@/components/chat/ChatInput";
import type { SendAgentTurn } from "@/components/chat/useAgentConversationStream";
import { toast } from "@/components/ui/toast";
import { registerParsedDocument } from "@/services/gerclaw/documents";
import {
  toFrontendCitation,
} from "@/services/gerclaw/conversation-history";
import type { AnswerVersion } from "@/services/gerclaw/run-contract";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import type {
  ChatActionType,
  ImageAttachment,
  Message,
  MessageBlock,
  Role,
} from "@/types";

interface ConversationControllerOptions {
  currentSessionId: string | null;
  chatAction: ChatActionType;
  role: Role;
  sendTurn: SendAgentTurn;
  stageSkillSelection: (sessionId: string, skillIds: string[]) => void;
  isSkillSelectionReady: (sessionId: string | null) => boolean;
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

export function useConversationController({
  currentSessionId,
  chatAction,
  role,
  sendTurn,
  stageSkillSelection,
  isSkillSelectionReady,
}: ConversationControllerOptions) {
  const loadedSkillIds = useAppStore((state) => state.loadedSkillIds);
  const setCurrentSession = useAppStore((state) => state.setCurrentSession);
  const messagesBySession = useChatStore((state) => state.messagesBySession);
  const updateMessage = useChatStore((state) => state.updateMessage);
  const createSession = useChatStore((state) => state.createSession);

  const prepareDocuments = useCallback(
    async (
      sessionId: string,
      documents: ChatDocumentAttachment[],
    ): Promise<Record<string, string>> => {
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
    [],
  );

  const handleRegenerate = (messageId: string) => {
    if (!currentSessionId) return;
    const messages = messagesBySession[currentSessionId] ?? [];
    const assistantIndex = messages.findIndex(
      (message) => message.id === messageId,
    );
    if (assistantIndex === -1) return;

    let userIndex = assistantIndex - 1;
    while (userIndex >= 0 && messages[userIndex].role !== "user") {
      userIndex -= 1;
    }
    if (userIndex < 0) return;

    const userMessage = messages[userIndex];
    const currentAnswer = messages[assistantIndex];
    if (!currentAnswer.answerGroupRunId || !currentAnswer.answerVersionId) {
      toast.show("请刷新对话以恢复服务端回答版本后再重新生成");
      return;
    }
    const images: ImageAttachment[] = userMessage.blocks
      .filter(
        (block): block is Extract<MessageBlock, { kind: "image" }> =>
          block.kind === "image",
      )
      .map((block) => block.data);
    sendTurn(
      currentSessionId,
      getMessageText(userMessage),
      true,
      images.length > 0 ? images : undefined,
      userMessage.uploadedFiles ?? [],
      currentAnswer.workflow ?? "standard",
      [],
      {
        sourceRunId: currentAnswer.answerGroupRunId,
        expectedCurrentAnswerVersionId: currentAnswer.answerVersionId,
      },
      messageId,
      currentAnswer,
    );
  };

  const handleAnswerVersionSelected = async (
    sessionId: string,
    messageId: string,
    version: AnswerVersion,
  ) => {
    if (!version.answer_markdown) {
      throw new Error("该回答版本正文已不可用");
    }
    const target = useChatStore
      .getState()
      .getMessages(sessionId)
      .find((message) => message.id === messageId);
    if (!target) return;
    updateMessage(messageId, {
      blocks: [
        {
          kind: "text",
          id: `block_${messageId}_${version.id}`,
          content: version.answer_markdown,
        },
      ],
      citations: version.citations.map(toFrontendCitation),
      answerGroupRunId: version.run_id,
      answerVersionId: version.id,
      answerVersion: version.version,
      executionRunId: version.producer_run_id,
      feedback: null,
      feedbackText: undefined,
    });
  };

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

    let sessionId = currentSessionId;
    if (!sessionId) {
      sessionId = createSession(role);
      if (workflow === "standard" && loadedSkillIds.length > 0) {
        stageSkillSelection(sessionId, loadedSkillIds);
      }
      setCurrentSession(sessionId);
    } else {
      const liveSessionId = useAppStore.getState().currentSessionId;
      if (
        liveSessionId !== sessionId ||
        (workflow === "standard" &&
          !isSkillSelectionReady(liveSessionId))
      ) {
        toast.show("正在恢复当前会话的技能，请稍候再发送");
        return false;
      }
    }

    try {
      const bindings = await prepareDocuments(sessionId, documents);
      sendTurn(
        sessionId,
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
        documentSessionId: sessionId,
      };
    } catch (error) {
      toast.show(
        error instanceof Error
          ? error.message
          : "文档无法安全加入本次对话",
      );
      return false;
    }
  };

  return {
    handleAnswerVersionSelected,
    handleRegenerate,
    handleSend,
  };
}
