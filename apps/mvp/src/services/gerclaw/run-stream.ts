import { GerclawApiError } from "./client";
import type { DurableStreamCursor } from "./durable-stream";
import { readAgentRun, readRecoverableRun } from "./runs";
import { getGerclawVisitorId } from "./visitor";

const RUN_RECONNECT_DELAYS_MS = [0, 250, 750] as const;

export type RunStreamConsumer = (
  response: Response,
  traceId: string,
  cursor: DurableStreamCursor
) => Promise<void>;

export function canReconnectStream(error: unknown): boolean {
  return (
    error instanceof TypeError ||
    (error instanceof GerclawApiError &&
      ["CHAT_STREAM_INCOMPLETE", "API_UNAVAILABLE", "RUN_RESOURCE_CONFLICT"].includes(
        error.code
      ))
  );
}

function waitForReconnect(delayMs: number, signal: AbortSignal): Promise<void> {
  if (delayMs === 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const handleAbort = () => {
      window.clearTimeout(timer);
      reject(new DOMException("Run reconnect cancelled", "AbortError"));
    };
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", handleAbort);
      resolve();
    }, delayMs);
    signal.addEventListener("abort", handleAbort, { once: true });
  });
}

async function resolveExactRecoverableRun(
  sessionId: string,
  traceId: string
): Promise<string | undefined> {
  const recoverable = await readRecoverableRun(sessionId);
  return recoverable.run?.trace_id === traceId ? recoverable.run.id : undefined;
}

async function openRunContinuation(
  runId: string,
  afterSequence: number,
  transportSignal: AbortSignal
): Promise<Response> {
  const run = await readAgentRun(runId);
  const path =
    run.status === "interrupted"
      ? `/api/gerclaw/runs/${encodeURIComponent(runId)}/resume`
      : `/api/gerclaw/runs/${encodeURIComponent(runId)}/stream?after_sequence=${afterSequence}`;
  return fetch(path, {
    method: run.status === "interrupted" ? "POST" : "GET",
    headers: {
      "X-GerClaw-Visitor-ID": getGerclawVisitorId(),
    },
    credentials: "same-origin",
    cache: "no-store",
    signal: transportSignal,
  });
}

export async function followDurableRun(
  options: {
    runId?: string;
    sessionId?: string;
    traceId: string;
    cursor: DurableStreamCursor;
  },
  transportSignal: AbortSignal,
  consume: RunStreamConsumer
): Promise<void> {
  let runId = options.runId ?? options.cursor.runId;
  let lastError: unknown;
  for (const delayMs of RUN_RECONNECT_DELAYS_MS) {
    await waitForReconnect(delayMs, transportSignal);
    try {
      runId =
        runId ??
        (options.sessionId
          ? await resolveExactRecoverableRun(options.sessionId, options.traceId)
          : undefined);
      if (!runId) {
        throw new GerclawApiError(
          "尚未找到可续传的回答",
          "CHAT_STREAM_INCOMPLETE",
          502,
          options.traceId
        );
      }
      const response = await openRunContinuation(
        runId,
        options.cursor.lastSequence,
        transportSignal
      );
      const traceId = response.headers.get("x-trace-id") ?? options.traceId;
      if (!response.ok || !response.body) {
        const payload = (await response.json().catch(() => null)) as {
          error?: { code?: string; message?: string };
        } | null;
        throw new GerclawApiError(
          payload?.error?.message ?? "回答续传暂时不可用",
          payload?.error?.code ?? "RUN_STREAM_FAILED",
          response.status,
          traceId
        );
      }
      await consume(response, traceId, options.cursor);
      return;
    } catch (error) {
      lastError = error;
      if (!canReconnectStream(error) || transportSignal.aborted) throw error;
    }
  }
  throw (
    lastError ??
    new GerclawApiError(
      "智能体连接提前中断，请重试",
      "CHAT_STREAM_INCOMPLETE",
      502,
      options.traceId
    )
  );
}
