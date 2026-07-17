import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import {
  getGerclawApiBaseUrl,
  isAllowedGerclawProxyTarget,
} from "@/server/gerclaw-api";
import { resolveGerclawAccess } from "@/server/gerclaw-access";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const proxyTraceIdSchema = z.string().regex(/^trace_[a-f0-9]{32}$/);

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

class ProxyBodyTooLargeError extends Error {}
class ProxyContentLengthError extends Error {}

function maxProxyBodyBytes(path: string): number {
  const voiceAsr = path === "voice/asr";
  const visionChat = path === "chat";
  const fallback = voiceAsr
    ? 10 * 1024 * 1024 + 2_048
    : visionChat
      ? 72 * 1024 * 1024
      : 1_200_000;
  const maximum = voiceAsr
    ? 10 * 1024 * 1024 + 2_048
    : visionChat
      ? 80 * 1024 * 1024
      : 2_097_152;
  const parsed = z.coerce
    .number()
    .int()
    .min(16_384)
    .max(maximum)
    .safeParse(
      voiceAsr
        ? (process.env.GERCLAW_MAX_VOICE_ASR_BODY_BYTES ?? String(fallback))
        : (process.env.GERCLAW_MAX_REQUEST_BODY_BYTES ?? String(fallback))
    );
  return parsed.success ? parsed.data : fallback;
}

async function readBoundedBody(request: NextRequest, path: string): Promise<ArrayBuffer | undefined> {
  if (request.method === "GET" || request.body === null) return undefined;
  const limit = maxProxyBodyBytes(path);
  const declared = request.headers.get("content-length");
  if (declared !== null) {
    if (!/^\d+$/.test(declared)) throw new ProxyContentLengthError();
    if (Number(declared) > limit) throw new ProxyBodyTooLargeError();
  }

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    received += value.byteLength;
    if (received > limit) {
      await reader.cancel();
      throw new ProxyBodyTooLargeError();
    }
    chunks.push(value);
  }
  const body = new ArrayBuffer(received);
  const view = new Uint8Array(body);
  let offset = 0;
  for (const chunk of chunks) {
    view.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

function responseHeaders(upstream: Response): Headers {
  const headers = new Headers();
  for (const name of ["content-type", "cache-control", "x-trace-id"]) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("X-Content-Type-Options", "nosniff");
  return headers;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path: segments } = await context.params;
  const path = segments.join("/");
  if (!isAllowedGerclawProxyTarget(path, request.method)) {
    return NextResponse.json(
      { error: { code: "PROXY_ROUTE_REJECTED", message: "请求路径不受支持" } },
      { status: 404 }
    );
  }

  let apiBase: string;
  try {
    apiBase = getGerclawApiBaseUrl();
  } catch {
    return NextResponse.json(
      { error: { code: "API_NOT_CONFIGURED", message: "后端服务尚未配置" } },
      { status: 503 }
    );
  }

  const query = request.nextUrl.search;
  const contentType = request.headers.get("content-type");
  const parsedTraceId = proxyTraceIdSchema.safeParse(request.headers.get("x-trace-id"));
  const traceId = parsedTraceId.success ? parsedTraceId.data : null;
  let body: ArrayBuffer | undefined;
  try {
    body = await readBoundedBody(request, path);
  } catch (error) {
    if (error instanceof ProxyBodyTooLargeError) {
      return NextResponse.json(
        { error: { code: "REQUEST_BODY_TOO_LARGE", message: "请求内容超过大小限制" } },
        { status: 413 }
      );
    }
    return NextResponse.json(
      { error: { code: "INVALID_CONTENT_LENGTH", message: "Content-Length 无效" } },
      { status: 400 }
    );
  }
  try {
    const access = await resolveGerclawAccess(request);

    const callUpstream = (token: string) => {
      const headers = new Headers({
        Accept: request.headers.get("accept") ?? "application/json",
        Authorization: `Bearer ${token}`,
      });
      if (contentType) headers.set("Content-Type", contentType);
      if (traceId) headers.set("X-Trace-ID", traceId);
      return fetch(`${apiBase}/api/v1/${path}${query}`, {
        method: request.method,
        headers,
        body,
        cache: "no-store",
        signal: request.signal,
      });
    };

    const upstream = await callUpstream(access.accessToken);
    const response = new NextResponse(upstream.body, {
      status: upstream.status,
      headers: responseHeaders(upstream),
    });
    access.applyCookies(response);
    return response;
  } catch (error) {
    if (error instanceof Error && error.message === "ACCOUNT_SESSION_REQUIRED") {
      return NextResponse.json(
        { error: { code: "AUTH_REQUIRED", message: "请先登录后继续" } },
        { status: 401 },
      );
    }
    return NextResponse.json(
      { error: { code: "API_UNAVAILABLE", message: "后端服务暂时不可用，请稍后重试" } },
      { status: 503 }
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
