import { NextRequest, NextResponse } from "next/server";
import { getGerclawApiBaseUrl } from "@/server/gerclaw-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const token = request.cookies.get("gerclaw_account_access")?.value;
  if (!token) return NextResponse.json({ error: { code: "AUTH_REQUIRED" } }, { status: 401 });
  const upstream = await fetch(
    `${getGerclawApiBaseUrl()}/api/v1/auth/admin/bad-cases${request.nextUrl.search}`,
    { headers: { Authorization: `Bearer ${token}`, Accept: "application/json" }, cache: "no-store" },
  );
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json", "cache-control": "no-store" },
  });
}
