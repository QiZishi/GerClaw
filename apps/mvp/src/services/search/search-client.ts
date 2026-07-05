import { searchConfig } from "@/lib/config";
import type { SearchResultItem } from "@/types/chat";
import { generateId } from "@/lib/format";
import {
  generateTraceId,
  fetchWithTimeout,
  classifyError,
  classifyHttpError,
} from "../api-client";

interface TavilySearchResult {
  title: string;
  url: string;
  content: string;
  score?: number;
  published_date?: string;
  raw_content?: string;
}

interface TavilyResponse {
  results?: TavilySearchResult[];
  answer?: string;
  query?: string;
  response_time?: number;
}

export async function searchTavily(query: string): Promise<SearchResultItem[]> {
  const traceId = generateTraceId();

  if (!searchConfig.tavilyApiKey) {
    return [];
  }

  try {
    const response = await fetchWithTimeout(
      "https://api.tavily.com/search",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          api_key: searchConfig.tavilyApiKey,
          query,
          search_depth: "basic",
          max_results: 5,
        }),
        timeoutMs: 15000,
      },
      15000
    );

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}`;
      try {
        const errorBody = await response.text();
        if (errorBody) {
          errorMessage = errorBody;
        }
      } catch {
        // ignore
      }
      throw classifyHttpError(response.status, errorMessage, traceId);
    }

    const data: TavilyResponse = await response.json();

    if (!data.results || !Array.isArray(data.results)) {
      return [];
    }

    return data.results.map((item) => {
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
    console.error("[search] Tavily search failed:", classifyError(error, traceId));
    return [];
  }
}

export async function search(query: string): Promise<SearchResultItem[]> {
  return searchTavily(query);
}
