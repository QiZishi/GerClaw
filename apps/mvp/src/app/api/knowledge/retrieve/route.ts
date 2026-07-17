import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const requestSchema = z.object({
  query: z.string().trim().min(1).max(4_000),
  maxResults: z.number().int().min(1).max(20).optional(),
}).strict();

const upstreamSchema = z.object({
  trace_id: z.string().min(1),
  results: z.array(z.object({
    content: z.string(),
    source: z.string(),
    score: z.number(),
    metadata: z.object({
      document_id: z.string(),
      chunk_id: z.string(),
      title: z.string(),
      category: z.string().optional(),
    }).passthrough(),
  }).passthrough()),
  medical_disclaimer: z.string(),
}).strict();

/**
 * Compatibility facade for the legacy knowledge client.  It delegates to the
 * authenticated GerClaw BFF so guest/account identity, rate limits, traces and
 * evidence retrieval remain server-owned rather than returning a fake response.
 */
export async function POST(request: NextRequest): Promise<Response> {
  const body = requestSchema.safeParse(await request.json().catch(() => null));
  if (!body.success) {
    return NextResponse.json({ success: false, error: "检索请求无效", chunks: [], total: 0 }, { status: 400 });
  }
  const upstream = await fetch(new URL("/api/gerclaw/rag/retrieve", request.url), {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(request.headers.get("cookie") ? { cookie: request.headers.get("cookie")! } : {}),
      ...(request.headers.get("x-gerclaw-visitor-id")
        ? { "x-gerclaw-visitor-id": request.headers.get("x-gerclaw-visitor-id")! }
        : {}),
    },
    body: JSON.stringify({ query: body.data.query, top_k: body.data.maxResults ?? 3 }),
    cache: "no-store",
  });
  const raw = await upstream.json().catch(() => null);
  if (!upstream.ok) {
    const response = NextResponse.json(
      { success: false, error: "本地知识库暂时不可用", chunks: [], total: 0 },
      { status: upstream.status },
    );
    const cookie = upstream.headers.get("set-cookie");
    if (cookie) response.headers.set("set-cookie", cookie);
    return response;
  }
  const result = upstreamSchema.safeParse(raw);
  if (!result.success) {
    return NextResponse.json({ success: false, error: "检索结果校验失败", chunks: [], total: 0 }, { status: 502 });
  }
  const response = NextResponse.json({
    success: true,
    traceId: result.data.trace_id,
    disclaimer: result.data.medical_disclaimer,
    chunks: result.data.results.map((item) => ({
      id: item.metadata.chunk_id,
      title: item.metadata.title,
      category: item.metadata.category ?? "未分类",
      content: item.content,
      filePath: item.source,
    })),
    total: result.data.results.length,
  });
  const cookie = upstream.headers.get("set-cookie");
  if (cookie) response.headers.set("set-cookie", cookie);
  return response;
}
