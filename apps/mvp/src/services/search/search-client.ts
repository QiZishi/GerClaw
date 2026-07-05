import type { SearchResultItem } from "@/types/chat";
import { generateId } from "@/lib/format";
import { generateTraceId, classifyError } from "../api-client";

interface SearchResult {
  title: string;
  url: string;
  content: string;
  score?: number;
  published_date?: string;
}

export async function search(query: string): Promise<SearchResultItem[]> {
  const traceId = generateTraceId();

  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Trace-Id": traceId,
      },
      body: JSON.stringify({
        query,
        maxResults: 5,
      }),
    });

    if (!response.ok) {
      console.warn("[search] Search API returned:", response.status);
      return [];
    }

    const data = await response.json();

    if (data.error) {
      console.warn("[search] Search API error:", data.error);
      return [];
    }

    const results: SearchResult[] = data.results || [];

    return results.map((item) => {
      let source = "";
      try {
        const url = new URL(item.url);
        source = url.hostname.replace(/^www\./, "");
      } catch {
        source = item.url;
      }

      return {
        id: generateId("search"),
        title: item.title || "无标题",
        url: item.url,
        source,
        snippet: item.content || "",
        publishedDate: item.published_date,
      } satisfies SearchResultItem;
    });
  } catch (error) {
    console.error("[search] Search failed:", classifyError(error, traceId));
    return [];
  }
}
