import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const TAVILY_API_KEY = process.env.NEXT_PUBLIC_TAVILY_API_KEY || "";
const ANYSEARCH_API_KEY = process.env.NEXT_PUBLIC_ANYSEARCH_API_KEY || "";

interface SearchResult {
  title: string;
  url: string;
  content: string;
  score?: number;
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { query, maxResults } = body;

  if (!query) {
    return Response.json({ error: "搜索关键词不能为空" }, { status: 400 });
  }

  // 优先使用 Tavily
  if (TAVILY_API_KEY) {
    try {
      const response = await fetch("https://api.tavily.com/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: TAVILY_API_KEY,
          query,
          max_results: maxResults || 5,
          include_answer: true,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        const results: SearchResult[] = (data.results || []).map((r: { title: string; url: string; content: string; score?: number }) => ({
          title: r.title,
          url: r.url,
          content: r.content,
          score: r.score,
        }));
        return Response.json({
          results,
          answer: data.answer || "",
          source: "tavily",
        });
      }
    } catch {
      // Tavily 失败，继续尝试备用
    }
  }

  // 备用：AnySearch（如果可用）
  if (ANYSEARCH_API_KEY) {
    try {
      const response = await fetch("https://api.anysearch.com/v1/search", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${ANYSEARCH_API_KEY}`,
        },
        body: JSON.stringify({
          query,
          max_results: maxResults || 5,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        const results: SearchResult[] = (data.results || []).map((r: { title: string; url: string; content: string; score?: number }) => ({
          title: r.title,
          url: r.url,
          content: r.content,
          score: r.score,
        }));
        return Response.json({
          results,
          answer: data.answer || "",
          source: "anysearch",
        });
      }
    } catch {
      // ignore
    }
  }

  return Response.json(
    { error: "搜索服务不可用，请检查环境变量配置" },
    { status: 503 }
  );
}
