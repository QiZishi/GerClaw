import { NextRequest, NextResponse } from "next/server";
import { getGerclawApiBaseUrl } from "@/server/gerclaw-api";

export const runtime = "nodejs";

export async function PATCH(request: NextRequest, context: { params: Promise<{ caseId: string }> }): Promise<Response> {
  const token = request.cookies.get("gerclaw_account_access")?.value;
  const csrf = request.cookies.get("gerclaw_account_csrf")?.value;
  if (!token || !csrf || csrf !== request.headers.get("x-gerclaw-csrf")) return NextResponse.json({ error: { code: "AUTH_REQUIRED" } }, { status: 401 });
  const { caseId } = await context.params;
  if (!/^[a-f0-9-]{36}$/.test(caseId)) return NextResponse.json({ error: { code: "BAD_CASE_NOT_FOUND" } }, { status: 404 });
  const upstream = await fetch(`${getGerclawApiBaseUrl()}/api/v1/auth/admin/bad-cases/${caseId}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${token}`, "content-type": "application/json", Accept: "application/json" },
    body: await request.text(), cache: "no-store",
  });
  return new NextResponse(upstream.body, { status: upstream.status, headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" } });
}
