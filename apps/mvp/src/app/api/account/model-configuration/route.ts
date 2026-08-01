import { NextRequest, NextResponse } from "next/server";
import { hasGerclawAccountAccess, resolveGerclawAccess } from "@/server/gerclaw-access";
import { getGerclawApiBaseUrl } from "@/server/gerclaw-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function proxy(request: NextRequest, method: "GET" | "PUT"): Promise<Response> {
  let access = await resolveGerclawAccess(request);
  let body: string | undefined;
  if (method === "PUT") {
    const payload = await request.json().catch(() => null);
    if (!payload || typeof payload !== "object") return NextResponse.json({ error: { code: "MODEL_CONFIGURATION_INPUT_INVALID" } }, { status: 422 });
    body = JSON.stringify(payload);
  }
  const call = (token: string) => fetch(`${getGerclawApiBaseUrl()}/api/v1/auth/model-configuration`, {
    method,
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) },
    body,
    cache: "no-store",
  });
  let upstream = await call(access.accessToken);
  if (upstream.status === 401 && !hasGerclawAccountAccess(request)) {
    access = await resolveGerclawAccess(request, { refreshGuest: true });
    upstream = await call(access.accessToken);
  }
  const response = new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json", "cache-control": "no-store" },
  });
  access.applyCookies(response);
  return response;
}

export function GET(request: NextRequest): Promise<Response> {
  return proxy(request, "GET");
}

export function PUT(request: NextRequest): Promise<Response> {
  return proxy(request, "PUT");
}
