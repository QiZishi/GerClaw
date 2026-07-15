import type { z } from "zod";
import { getGerclawVisitorId } from "./visitor";

interface GerclawErrorBody {
  error?: { code?: string; message?: string };
  detail?: { code?: string; message?: string } | string;
}

export class GerclawApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status: number,
    readonly traceId?: string
  ) {
    super(message);
    this.name = "GerclawApiError";
  }
}

export async function gerclawRequest<T>(
  path: string,
  schema: z.ZodType<T>,
  init: RequestInit = {}
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Accept", "application/json");
  headers.set("X-GerClaw-Visitor-ID", getGerclawVisitorId());
  const response = await fetch(`/api/gerclaw/${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  const traceId = response.headers.get("x-trace-id") ?? undefined;
  const body = (await response.json().catch(() => null)) as GerclawErrorBody | null;
  if (!response.ok) {
    const detail = body?.error ?? (typeof body?.detail === "object" ? body.detail : undefined);
    throw new GerclawApiError(
      detail?.message ?? "请求未完成，请稍后重试",
      detail?.code ?? "GERCLAW_REQUEST_FAILED",
      response.status,
      traceId
    );
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new GerclawApiError("后端响应格式不正确", "GERCLAW_RESPONSE_INVALID", 502, traceId);
  }
  return parsed.data;
}
