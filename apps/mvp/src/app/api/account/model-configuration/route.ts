import { NextRequest, NextResponse } from "next/server";
import { getGerclawApiBaseUrl } from "@/server/gerclaw-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function accessToken(request: NextRequest): string | null {
  return request.cookies.get("gerclaw_account_access")?.value ?? null;
}

async function proxy(request: NextRequest, method: "GET" | "PUT"): Promise<Response> {
  const token = accessToken(request);
  if (!token) return NextResponse.json({ error: { code: "AUTH_REQUIRED" } }, { status: 401 });
  const headers: Record<string, string> = { Authorization: `Bearer ${token}`, Accept: "application/json" };
  let body: string | undefined;
  if (method === "PUT") {
    const payload = await request.json().catch(() => null);
    if (!payload || typeof payload !== "object") return NextResponse.json({ error: { code: "MODEL_CONFIGURATION_INPUT_INVALID" } }, { status: 422 });
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(payload);
  }
  const upstream = await fetch(`${getGerclawApiBaseUrl()}/api/v1/auth/model-configuration`, { method, headers, body, cache: "no-store" });
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json", "cache-control": "no-store" },
  });
}

export function GET(request: NextRequest): Promise<Response> {
  return proxy(request, "GET");
}

export function PUT(request: NextRequest): Promise<Response> {
  return proxy(request, "PUT");
}
