import "server-only";

import { z } from "zod";
import {
  SearchRequestError,
  statusIsRetryable,
  withPrimaryFallback,
} from "@/server/search-retry";

const anySearchResponseSchema = z.object({
  jsonrpc: z.literal("2.0"),
  result: z
    .object({
      content: z.array(z.object({ type: z.literal("text"), text: z.string().min(1) })).min(1),
      isError: z.boolean().optional(),
    })
    .optional(),
  error: z.object({ message: z.string() }).optional(),
});

const tavilyResponseSchema = z.object({
  results: z
    .array(
      z.object({
        title: z.string().min(1),
        url: z.string().url(),
        content: z.string().min(1),
        published_date: z.string().optional(),
        score: z.number().min(0).max(1).optional(),
      })
    )
    .default([]),
});

export interface ServerSearchResult {
  title: string;
  url: string;
  content: string;
  published_date?: string;
  score?: number;
}

export interface ServerSearchResponse {
  results: ServerSearchResult[];
  source: "anysearch" | "tavily";
}

const ANYSEARCH_URL = process.env.ANYSEARCH_URL || "";
const ANYSEARCH_API_KEY = process.env.ANYSEARCH_API_KEY || "";
const TAVILY_URL = process.env.TAVILY_URL || "";
const TAVILY_API_KEY = process.env.TAVILY_API_KEY || "";
const SEARCH_TIMEOUT_MS = 10_000;

async function fetchProvider(url: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new SearchRequestError("Search provider network request failed", true);
  }
  if (!response.ok) {
    throw new SearchRequestError(
      `Search provider rejected request (${response.status})`,
      statusIsRetryable(response.status)
    );
  }
  return response;
}

function endpoint(baseUrl: string, suffix: string): string {
  const normalized = baseUrl.replace(/\/+$/, "");
  return normalized.endsWith(suffix) ? normalized : `${normalized}${suffix}`;
}

function sanitizeQuery(query: string): string {
  return query
    .replace(/(?<!\d)1[3-9]\d{9}(?!\d)/g, "[PHONE]")
    .replace(
      /(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)/g,
      "[ID_CARD]"
    )
    .replace(/[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,189}\.[A-Za-z]{2,63}/g, "[EMAIL]")
    .replace(/(?:我叫|姓名(?:是|为|[:：])?|患者姓名(?:是|为|[:：])?)\s*[\u4e00-\u9fff]{2,4}/g, "患者")
    .trim();
}

function parseAnySearchMarkdown(markdown: string, maxResults: number): ServerSearchResult[] {
  const headings = [...markdown.matchAll(/^###\s+\d+\.\s+(.+?)\s*$/gm)];
  return headings
    .slice(0, maxResults)
    .flatMap((heading, index) => {
      const start = (heading.index ?? 0) + heading[0].length;
      const end = headings[index + 1]?.index ?? markdown.length;
      const body = markdown.slice(start, end);
      const url = body.match(/^-\s+\*\*URL\*\*:\s*(https:\/\/\S+)\s*$/m)?.[1]?.replace(/[.,)]$/, "");
      const content = body
        .split("\n")
        .filter((line) => line.trim() && !line.includes("**URL**:"))
        .map((line) => line.replace(/^-\s+/, "").trim())
        .join(" ")
        .slice(0, 4_000);
      if (!url || !content) return [];
      const publishedDate = content.match(/\b(?:19|20)\d{2}[-/.](?:0?[1-9]|1[0-2])(?:[-/.](?:0?[1-9]|[12]\d|3[01]))?\b/)?.[0];
      return [
        {
          title: heading[1].slice(0, 512),
          url,
          content,
          published_date: publishedDate,
        },
      ];
    });
}

async function callAnySearch(query: string, maxResults: number): Promise<ServerSearchResult[]> {
  if (!ANYSEARCH_URL) throw new Error("AnySearch is not configured");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (ANYSEARCH_API_KEY) headers.Authorization = `Bearer ${ANYSEARCH_API_KEY}`;
  const response = await fetchProvider(endpoint(ANYSEARCH_URL, "/mcp"), {
    method: "POST",
    headers,
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: crypto.randomUUID(),
      method: "tools/call",
      params: {
        name: "search",
        arguments: { query, max_results: maxResults, domain: "health" },
      },
    }),
    signal: AbortSignal.timeout(SEARCH_TIMEOUT_MS),
  });
  const payload = anySearchResponseSchema.parse(await response.json());
  if (payload.error || !payload.result || payload.result.isError) {
    throw new Error("AnySearch tool call failed");
  }
  const markdown = payload.result.content.map((item) => item.text).join("\n");
  const results = parseAnySearchMarkdown(markdown, maxResults);
  if (results.length === 0 && !/\b(?:0 results|no results)\b/i.test(markdown)) {
    throw new Error("AnySearch returned an invalid result format");
  }
  return results;
}

async function callTavily(query: string, maxResults: number): Promise<ServerSearchResult[]> {
  if (!TAVILY_URL || !TAVILY_API_KEY) throw new Error("Tavily is not configured");
  const response = await fetchProvider(endpoint(TAVILY_URL, "/search"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${TAVILY_API_KEY}`,
    },
    body: JSON.stringify({
      query,
      max_results: maxResults,
      search_depth: "advanced",
      include_answer: false,
    }),
    signal: AbortSignal.timeout(SEARCH_TIMEOUT_MS),
  });
  const payload = tavilyResponseSchema.parse(await response.json());
  return payload.results;
}

export async function searchWeb(query: string, maxResults = 6): Promise<ServerSearchResponse> {
  const safeQuery = sanitizeQuery(query);
  if (!safeQuery) throw new Error("搜索关键词不能为空");
  const boundedResults = Math.min(10, Math.max(1, maxResults));

  const routed = await withPrimaryFallback(
    () => callAnySearch(safeQuery, boundedResults),
    () => callTavily(safeQuery, boundedResults)
  );
  return {
    results: routed.value,
    source: routed.fallbackUsed ? "tavily" : "anysearch",
  };
}
