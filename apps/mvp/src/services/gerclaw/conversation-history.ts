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

/** Account-only history; guest tokens are rejected by the API. */
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

function toCitation(
  source: BackendSessionMessages["messages"][number]["citations"][number],
  index: number
): Citation {
  return {
    id: index + 1,
    title: source.title,
    snippet: source.excerpt,
    url: source.corpus === "web" ? source.locator : "",
    source:
      source.corpus === "local_knowledge_base"
        ? "本地知识库"
        : source.corpus === "uploaded_document"
          ? "上传文档"
          : source.corpus === "uploaded_image"
            ? "上传图片"
            : source.locator,
  };
}

/** Convert the validated owner-visible API projection into presentation blocks. */
export function toFrontendMessages(response: BackendSessionMessages): Message[] {
  return response.messages.map((item) => {
    const citations = item.citations.map(toCitation);
    return {
      id: item.id,
      sessionId: response.session_id,
      role: item.role,
      blocks: [{ kind: "text", id: `block_${item.id}`, content: item.text }],
      citations,
      status: "done",
      createdAt: Date.parse(item.created_at),
      hasDisclaimer: item.role === "assistant",
      traceId: item.trace_id ?? undefined,
      workflow: "standard",
    };
  });
}
