import { NextRequest, NextResponse } from "next/server";
import { createHmac } from "node:crypto";
import { z } from "zod";
import {
  getGerclawApiBaseUrl,
  isAllowedGerclawProxyTarget,
} from "@/server/gerclaw-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const COOKIE_NAME = "gerclaw_guest_token";
const ACCOUNT_COOKIE_NAME = "gerclaw_account_access";
const VISITOR_COOKIE_NAME = "gerclaw_visitor_id";
const visitorIdSchema = z.string().regex(/^[a-f0-9]{32}$/);
const proxyTraceIdSchema = z.string().regex(/^trace_[a-f0-9]{32}$/);
const guestTokenSchema = z
  .object({
    access_token: z.string().min(32),
    expires_in: z.number().int().min(300).max(86_400),
  })
  .passthrough();

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

interface GuestCredential {
  accessToken: string;
  expiresIn: number;
}

class ProxyBodyTooLargeError extends Error {}
class ProxyContentLengthError extends Error {}

function maxProxyBodyBytes(): number {
  const parsed = z.coerce
    .number()
    .int()
    .min(16_384)
    .max(2_097_152)
    .safeParse(process.env.GERCLAW_MAX_REQUEST_BODY_BYTES ?? "1200000");
  return parsed.success ? parsed.data : 1_200_000;
}

async function readBoundedBody(request: NextRequest): Promise<ArrayBuffer | undefined> {
  if (request.method === "GET" || request.body === null) return undefined;
  const limit = maxProxyBodyBytes();
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

function visitorSignature(visitorId: string): string {
  const secret = z
    .string()
    .min(32)
    .parse(process.env.GERCLAW_GUEST_IDENTITY_SECRET);
  return createHmac("sha256", secret)
    .update(`gerclaw-guest-bootstrap:v1:${visitorId}`)
    .digest("hex");
}

async function issueGuestCredential(
  apiBase: string,
  visitorId: string
): Promise<GuestCredential> {
  const response = await fetch(`${apiBase}/api/v1/auth/guest`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "X-GerClaw-Visitor-ID": visitorId,
      "X-GerClaw-Visitor-Signature": visitorSignature(visitorId),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("访客身份服务暂时不可用");
  }
  const parsed = guestTokenSchema.safeParse(await response.json().catch(() => null));
  if (!parsed.success) {
    throw new Error("访客身份响应格式不正确");
  }
  return {
    accessToken: parsed.data.access_token,
    expiresIn: parsed.data.expires_in,
  };
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
    body = await readBoundedBody(request);
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
  let credential: GuestCredential | null = null;
  const accountAccessToken = request.cookies.get(ACCOUNT_COOKIE_NAME)?.value;
  let accessToken = accountAccessToken ?? request.cookies.get(COOKIE_NAME)?.value;
  const cookieVisitorId = visitorIdSchema.safeParse(
    request.cookies.get(VISITOR_COOKIE_NAME)?.value
  );
  const headerVisitorId = visitorIdSchema.safeParse(
    request.headers.get("x-gerclaw-visitor-id")
  );
  let visitorId: string | null = null;
  if (accountAccessToken) {
    // Account access is server-issued and must not be rebound to a visitor identity.
  } else if (cookieVisitorId.success) {
    visitorId = cookieVisitorId.data;
  } else if (headerVisitorId.success) {
    visitorId = headerVisitorId.data;
  } else {
    return NextResponse.json(
      { error: { code: "VISITOR_ID_REQUIRED", message: "访客身份尚未初始化，请刷新后重试" } },
      { status: 400 }
    );
  }
  const visitorCookieRequired = !accountAccessToken && !cookieVisitorId.success;
  if (visitorCookieRequired) {
    // A token without its identity cookie cannot be proven to match the client-generated ID.
    accessToken = undefined;
  }

  try {
    if (!accessToken) {
      credential = await issueGuestCredential(apiBase, visitorId!);
      accessToken = credential.accessToken;
    }

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

    let upstream = await callUpstream(accessToken);
    if (upstream.status === 401 && !accountAccessToken) {
      credential = await issueGuestCredential(apiBase, visitorId!);
      accessToken = credential.accessToken;
      upstream = await callUpstream(accessToken);
    }

    const response = new NextResponse(upstream.body, {
      status: upstream.status,
      headers: responseHeaders(upstream),
    });
    if (credential) {
      response.cookies.set(COOKIE_NAME, credential.accessToken, {
        httpOnly: true,
        sameSite: "lax",
        secure: process.env.NODE_ENV === "production",
        path: "/",
        maxAge: credential.expiresIn,
      });
    }
    if (visitorCookieRequired && visitorId !== null) {
      response.cookies.set(VISITOR_COOKIE_NAME, visitorId, {
        httpOnly: true,
        sameSite: "lax",
        secure: process.env.NODE_ENV === "production",
        path: "/",
        maxAge: 31_536_000,
      });
    }
    return response;
  } catch {
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
