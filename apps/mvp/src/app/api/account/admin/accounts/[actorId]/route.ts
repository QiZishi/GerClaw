import { NextRequest, NextResponse } from "next/server";
import { getGerclawApiBaseUrl } from "@/server/gerclaw-api";

export const runtime = "nodejs";

export async function PATCH(request: NextRequest, context: { params: Promise<{ actorId: string }> }): Promise<Response> {
  const token = request.cookies.get("gerclaw_account_access")?.value;
  const csrf = request.cookies.get("gerclaw_account_csrf")?.value;
  if (!token || !csrf || csrf !== request.headers.get("x-gerclaw-csrf")) return NextResponse.json({ error: { code: "AUTH_REQUIRED" } }, { status: 401 });
  const { actorId } = await context.params;
  if (!/^usr_account_[a-f0-9]{32}$/.test(actorId)) return NextResponse.json({ error: { code: "ACCOUNT_NOT_FOUND" } }, { status: 404 });
  const body = await request.text();
  const upstream = await fetch(`${getGerclawApiBaseUrl()}/api/v1/auth/admin/accounts/${actorId}`, { method: "PATCH", headers: { Authorization: `Bearer ${token}`, "content-type": "application/json", Accept: "application/json" }, body, cache: "no-store" });
  return new NextResponse(upstream.body, { status: upstream.status, headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" } });
}
