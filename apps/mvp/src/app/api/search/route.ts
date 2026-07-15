import { NextRequest } from "next/server";
import { z } from "zod";
import { searchWeb } from "@/server/search";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const searchRequestSchema = z
  .object({
    query: z.string().trim().min(1).max(4_000),
    maxResults: z.coerce.number().int().min(1).max(10).optional(),
  })
  .strict();

export async function POST(request: NextRequest) {
  const parsed = searchRequestSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return Response.json({ error: "搜索关键词不能为空" }, { status: 400 });
  }

  try {
    return Response.json(
      await searchWeb(parsed.data.query, parsed.data.maxResults ?? 6)
    );
  } catch {
    return Response.json(
      { error: "搜索服务暂时不可用，请稍后重试" },
      { status: 503 }
    );
  }
}
