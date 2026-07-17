import { z } from "zod";
import { GerclawApiError, gerclawRequest } from "./client";
import { chatDoneEventSchema } from "./chat-contract";
import { ensureBackendSession } from "./skills";
import { getGerclawVisitorId } from "./visitor";
import type { Citation, ImageAttachment } from "@/types";

const textDeltaSchema = z.object({ content: z.string() }).passthrough();
const thinkingSchema = z.object({ content: z.string(), status: z.string() }).passthrough();
const toolCallSchema = z
  .object({ tool_call_id: z.string(), tool_name: z.string(), status: z.string() })
  .passthrough();
const toolResultSchema = z
  .object({
    tool_call_id: z.string(),
    tool_name: z.string(),
    status: z.string(),
    duration_ms: z.number().int().nonnegative(),
    results: z.array(z.unknown()).optional(),
  })
  .passthrough();
type ChatReference = z.infer<typeof chatDoneEventSchema>["references"][number];
const errorSchema = z
  .object({
    code: z.string(),
    message: z.string(),
    trace_id: z.string(),
    retriable: z.boolean(),
  })
  .passthrough();
const cancelledSchema = z
  .object({
    trace_id: z.string(),
    status: z.literal("cancelled"),
    message: z.string(),
  })
  .strict();
const cancellationRequestedSchema = z
  .object({
    trace_id: z.string(),
    status: z.literal("cancellation_requested"),
  })
  .strict();
const approvalRequiredSchema = z
  .object({
    approval_id: z.string().uuid(),
    tool_name: z.string().min(1),
    status: z.literal("pending"),
    expires_at: z.string().datetime(),
    policy_version: z.string().min(1),
    tool_version: z.string().min(1),
  })
  .strict();
const safetyNoticeSchema = z
  .object({
    codes: z.array(z.string().min(1).max(80)).min(1).max(10),
    content: z.string().min(1).max(1_000),
  })
  // SSE middleware appends observability fields (for example timestamp).
  // Keep the safety payload fail-closed for its required fields while allowing
  // transport metadata to evolve independently.
  .passthrough();

export interface AgentToolEvent {
  id: string;
  name: string;
  status: string;
  durationMs?: number;
  results?: unknown[];
}

export interface AgentChatCallbacks {
  onThinking?: (content: string) => void;
  onText?: (delta: string) => void;
  onToolCall?: (event: AgentToolEvent) => void;
  onToolResult?: (event: AgentToolEvent) => void;
  onApprovalRequired?: (approval: {
    id: string;
    toolName: string;
    expiresAt: string;
    policyVersion: string;
    toolVersion: string;
  }) => void;
  onSafetyNotice?: (notice: { codes: string[]; content: string }) => void;
  onDone?: (fullText: string, citations: Citation[], traceId: string) => void;
  onCancelled?: (traceId: string, message: string) => void;
  onError?: (error: GerclawApiError) => void;
}

async function requestAgentCancellation(traceId: string): Promise<void> {
  await gerclawRequest(
    `chat/${traceId}/cancel`,
    cancellationRequestedSchema,
    { method: "POST" }
  );
}

function toCitation(
  reference: ChatReference,
  index: number
): Citation {
  return {
    id: index + 1,
    title: reference.title,
    snippet: reference.excerpt,
    url: reference.corpus === "web" ? reference.locator : "",
    source:
      reference.corpus === "local_knowledge_base"
        ? "本地知识库"
        : reference.corpus === "uploaded_document"
          ? "上传文档"
          : reference.corpus === "uploaded_image"
            ? "上传图片"
          : reference.locator,
  };
}

function parseEventBlock(block: string): { event: string; data: unknown } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    throw new GerclawApiError("流式响应格式不正确", "CHAT_STREAM_INVALID", 502);
  }
}

export async function streamAgentChat(
  input: {
    localSessionId: string;
    message: string;
    loadedSkills: string[];
    uploadedDocumentIds?: string[];
    images?: ImageAttachment[];
    /** Companion has an isolated, no-tool backend policy. */
    workflow?: "standard" | "companion";
  },
  signal: AbortSignal,
  callbacks: AgentChatCallbacks
): Promise<void> {
  let traceId = `trace_${crypto.randomUUID().replaceAll("-", "")}`;
  const transportController = new AbortController();
  let requestStarted = false;
  let cancellationFailureReported = false;
  const handleCancellationRequest = () => {
    if (!requestStarted) return;
    void requestAgentCancellation(traceId).catch((error) => {
      cancellationFailureReported = true;
      transportController.abort();
      callbacks.onError?.(
        error instanceof GerclawApiError
          ? error
          : new GerclawApiError(
              "暂时无法安全停止，请稍后重试",
              "CHAT_CANCELLATION_UNAVAILABLE",
              503,
              traceId
            )
      );
    });
  };
  signal.addEventListener("abort", handleCancellationRequest, { once: true });
  try {
    const sessionId = await ensureBackendSession(input.localSessionId);
    if (signal.aborted) {
      callbacks.onCancelled?.(traceId, "回答已在发送前停止。");
      return;
    }
    requestStarted = true;
    const response = await fetch("/api/gerclaw/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Trace-ID": traceId,
        "X-GerClaw-Visitor-ID": getGerclawVisitorId(),
      },
      body: JSON.stringify({
        session_id: sessionId,
        message: input.message,
        loaded_skills: input.loadedSkills,
        uploaded_files: input.uploadedDocumentIds ?? [],
        images: (input.images ?? []).map((image) => ({
          media_type: image.mimeType,
          base64: image.base64,
        })),
        channel: "web",
        workflow: input.workflow ?? "standard",
      }),
      credentials: "same-origin",
      cache: "no-store",
      signal: transportController.signal,
    });
    traceId = response.headers.get("x-trace-id") ?? traceId;
    if (!response.ok || !response.body) {
      const payload = (await response.json().catch(() => null)) as {
        error?: { code?: string; message?: string };
      } | null;
      throw new GerclawApiError(
        payload?.error?.message ?? "智能体服务暂时不可用",
        payload?.error?.code ?? "CHAT_REQUEST_FAILED",
        response.status,
        traceId
      );
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let sawTerminal = false;

    const processBlock = (block: string) => {
      const parsed = parseEventBlock(block);
      if (!parsed) return;
      if (parsed.event === "text_delta") {
        callbacks.onText?.(textDeltaSchema.parse(parsed.data).content);
      } else if (parsed.event === "thinking") {
        callbacks.onThinking?.(thinkingSchema.parse(parsed.data).content);
      } else if (parsed.event === "tool_call") {
        const tool = toolCallSchema.parse(parsed.data);
        callbacks.onToolCall?.({ id: tool.tool_call_id, name: tool.tool_name, status: tool.status });
      } else if (parsed.event === "tool_result") {
        const tool = toolResultSchema.parse(parsed.data);
        callbacks.onToolResult?.({
          id: tool.tool_call_id,
          name: tool.tool_name,
          status: tool.status,
          durationMs: tool.duration_ms,
          results: tool.results,
        });
      } else if (parsed.event === "approval_required") {
        const approval = approvalRequiredSchema.parse(parsed.data);
        callbacks.onApprovalRequired?.({
          id: approval.approval_id,
          toolName: approval.tool_name,
          expiresAt: approval.expires_at,
          policyVersion: approval.policy_version,
          toolVersion: approval.tool_version,
        });
      } else if (parsed.event === "safety_notice") {
        const notice = safetyNoticeSchema.parse(parsed.data);
        callbacks.onSafetyNotice?.(notice);
      } else if (parsed.event === "done") {
        const doneEvent = chatDoneEventSchema.parse(parsed.data);
        sawTerminal = true;
        callbacks.onDone?.(
          doneEvent.full_text,
          doneEvent.references.map(toCitation),
          doneEvent.trace_id
        );
      } else if (parsed.event === "cancelled") {
        const cancelled = cancelledSchema.parse(parsed.data);
        sawTerminal = true;
        callbacks.onCancelled?.(cancelled.trace_id, cancelled.message);
      } else if (parsed.event === "error") {
        const error = errorSchema.parse(parsed.data);
        throw new GerclawApiError(error.message, error.code, 500, error.trace_id);
      }
    };

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true }).replaceAll("\r\n", "\n");
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";
        for (const block of blocks) {
          processBlock(block);
        }
      }
      buffer += decoder.decode().replaceAll("\r\n", "\n");
      if (buffer.trim()) processBlock(buffer);
      if (!sawTerminal) {
        throw new GerclawApiError(
          "智能体连接提前中断，请重试",
          "CHAT_STREAM_INCOMPLETE",
          502,
          traceId
        );
      }
    } finally {
      try {
        reader.releaseLock();
      } catch {
        // Abort can invalidate the reader before cleanup; the request is already cancelled.
      }
    }
  } catch (error) {
    if (cancellationFailureReported) return;
    const apiError =
      error instanceof GerclawApiError
        ? error
        : new GerclawApiError(
            error instanceof Error ? error.message : "智能体调用失败",
            "CHAT_CLIENT_FAILED",
            500,
            traceId
          );
    callbacks.onError?.(apiError);
  } finally {
    signal.removeEventListener("abort", handleCancellationRequest);
  }
}
