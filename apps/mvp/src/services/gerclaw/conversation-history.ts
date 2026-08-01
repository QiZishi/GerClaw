"use client";

import { gerclawRequest } from "./client";
import {
  sessionListSchema,
  sessionMessagesSchema,
  type BackendSession,
  type BackendSessionMessages,
} from "./schemas";
import { toFrontendSession } from "./conversation-session-presenter";
import type { Citation, Message, Session } from "@/types";

/** Durable history is account-only; guest conversations remain session-local in the UI. */
export async function listConversationHistory(): Promise<BackendSession[]> {
  const result = await gerclawRequest("sessions", sessionListSchema);
  return result.sessions;
}

export async function readConversationMessages(
  sessionId: string
): Promise<BackendSessionMessages> {
  return gerclawRequest(
    `sessions/${encodeURIComponent(sessionId)}/messages`,
    sessionMessagesSchema
  );
}

export function toFrontendSessions(items: BackendSession[], role: Session["role"]): Session[] {
  return items.map((item) => toFrontendSession(item, role));
}

export function toFrontendCitation(
  source: BackendSessionMessages["messages"][number]["citations"][number],
  index: number
): Citation {
  return {
    id: index + 1,
    title: source.title,
    snippet: source.excerpt,
    locator: source.locator,
    url: source.corpus === "web" ? source.locator : "",
    source:
      source.corpus === "local_knowledge_base"
        ? "本地知识库"
        : source.corpus === "uploaded_document"
          ? "上传文档"
          : source.corpus === "uploaded_image"
            ? "上传图片"
            : source.locator,
    corpus: source.corpus,
  };
}

/** Convert the validated owner-visible API projection into presentation blocks. */
export function toFrontendMessages(response: BackendSessionMessages): Message[] {
  return response.messages.map((item) => {
    const citations = item.citations.map(toFrontendCitation);
    return {
      id: item.id,
      sessionId: response.session_id,
      role: item.role,
      blocks: [{ kind: "text", id: `block_${item.id}`, content: item.text }],
      citations,
      status: "done",
      createdAt: Date.parse(item.created_at),
      hasDisclaimer:
        item.role === "assistant" && item.text.includes("内容由 AI 生成，仅供参考。"),
      traceId: item.trace_id ?? undefined,
      answerGroupRunId: item.answer_group_run_id ?? undefined,
      answerVersionId: item.answer_version_id ?? undefined,
      answerVersion: item.answer_version ?? undefined,
      workflow: "standard",
    };
  });
}
