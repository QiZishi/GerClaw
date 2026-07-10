import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIMARY_URL = process.env.NEXT_PUBLIC_PRIMARY_URL || "";
const PRIMARY_API_KEY = process.env.NEXT_PUBLIC_PRIMARY_API_KEY || "";
const PRIMARY_MODEL = process.env.NEXT_PUBLIC_PRIMARY_MODEL || "gpt-4o";

const BACKUP1_URL = process.env.NEXT_PUBLIC_BACKUP1_URL || "";
const BACKUP1_API_KEY = process.env.NEXT_PUBLIC_BACKUP1_API_KEY || "";
const BACKUP1_MODEL = process.env.NEXT_PUBLIC_BACKUP1_MODEL || "";

const BACKUP2_URL = process.env.NEXT_PUBLIC_BACKUP2_URL || "";
const BACKUP2_API_KEY = process.env.NEXT_PUBLIC_BACKUP2_API_KEY || "";
const BACKUP2_MODEL = process.env.NEXT_PUBLIC_BACKUP2_MODEL || "";

const TAVILY_API_KEY = process.env.NEXT_PUBLIC_TAVILY_API_KEY || "";
const ANYSEARCH_API_KEY = process.env.NEXT_PUBLIC_ANYSEARCH_API_KEY || "";

interface ModelConfig {
  url: string;
  apiKey: string;
  modelName: string;
}

interface ToolCallState {
  id: string;
  name: string;
  index: number;
  argsJson: string;
}

function getModels(): ModelConfig[] {
  const models: ModelConfig[] = [];
  if (PRIMARY_URL && PRIMARY_API_KEY) {
    models.push({ url: PRIMARY_URL, apiKey: PRIMARY_API_KEY, modelName: PRIMARY_MODEL });
  }
  if (BACKUP1_URL && BACKUP1_API_KEY) {
    models.push({ url: BACKUP1_URL, apiKey: BACKUP1_API_KEY, modelName: BACKUP1_MODEL });
  }
  if (BACKUP2_URL && BACKUP2_API_KEY) {
    models.push({ url: BACKUP2_URL, apiKey: BACKUP2_API_KEY, modelName: BACKUP2_MODEL });
  }
  return models;
}

function buildChatUrl(baseUrl: string): string {
  const trimmed = baseUrl.replace(/\/+$/, "");
  if (trimmed.endsWith("/chat/completions")) return trimmed;
  return `${trimmed}/chat/completions`;
}

const WEB_SEARCH_TOOL = {
  type: "function" as const,
  function: {
    name: "web_search",
    description: "搜索互联网获取最新信息、医学指南、新闻动态等实时内容",
    parameters: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "搜索关键词",
        },
      },
      required: ["query"],
    },
  },
};

async function executeWebSearch(query: string): Promise<unknown> {
  const maxResults = 5;

  if (TAVILY_API_KEY) {
    try {
      const response = await fetch("https://api.tavily.com/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: TAVILY_API_KEY,
          query,
          max_results: maxResults,
          include_answer: true,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        const results = (data.results || []).map((r: { title: string; url: string; content: string; published_date?: string }) => ({
          title: r.title,
          url: r.url,
          content: r.content,
          published_date: r.published_date,
        }));
        return {
          answer: data.answer || "",
          results,
          source: "tavily",
        };
      }
    } catch {
      // fall through
    }
  }

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
          max_results: maxResults,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        const results = (data.results || []).map((r: { title: string; url: string; content: string; published_date?: string }) => ({
          title: r.title,
          url: r.url,
          content: r.content,
          published_date: r.published_date,
        }));
        return {
          answer: data.answer || "",
          results,
          source: "anysearch",
        };
      }
    } catch {
      // fall through
    }
  }

  return {
    answer: "",
    results: [],
    error: "搜索服务不可用",
  };
}

async function executeTool(name: string, args: Record<string, unknown>): Promise<unknown> {
  if (name === "web_search") {
    const query = String(args.query || "");
    if (!query) return { error: "搜索关键词不能为空" };
    return executeWebSearch(query);
  }
  return { error: `未知工具: ${name}` };
}

async function streamWithTools(
  model: ModelConfig,
  messages: Record<string, unknown>[],
  tools: Record<string, unknown>[] | undefined,
  temperature: number,
  maxTokens: number | undefined,
  encoder: TextEncoder,
  controller: ReadableStreamDefaultController,
  abortSignal: AbortSignal
): Promise<void> {
  const currentMessages = [...messages];
  const maxIterations = 5;

  for (let iteration = 0; iteration < maxIterations; iteration++) {
    const url = buildChatUrl(model.url);
    const reqBody: Record<string, unknown> = {
      model: model.modelName,
      messages: currentMessages,
      stream: true,
      temperature,
      enable_thinking: true,
    };
    if (maxTokens) {
      reqBody.max_tokens = maxTokens;
    }
    if (tools && tools.length > 0) {
      reqBody.tools = tools;
      reqBody.tool_choice = "auto";
    }

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${model.apiKey}`,
      },
      body: JSON.stringify(reqBody),
      signal: abortSignal,
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errText}`);
    }

    if (!response.body) {
      throw new Error("响应体为空");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const toolCalls: ToolCallState[] = [];
    let finishReason: string | null = null;
    let thinkingEnded = false;

    try {
      while (true) {
        if (abortSignal.aborted) {
          controller.close();
          return;
        }
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith("data: ")) continue;

          const data = trimmed.slice(6);
          if (data === "[DONE]") continue;

          try {
            const json = JSON.parse(data);
            const choice = json.choices?.[0];
            if (!choice) continue;

            if (choice.finish_reason) {
              finishReason = choice.finish_reason;
            }

            const delta = choice.delta;
            if (!delta) continue;

            const thinkingDelta = delta.reasoning_content || delta.thinking;
            if (thinkingDelta) {
              controller.enqueue(
                encoder.encode(`data: ${JSON.stringify({ type: "thinking", delta: thinkingDelta })}\n\n`)
              );
            }

            if (delta.content) {
              if (!thinkingEnded) {
                controller.enqueue(
                  encoder.encode(`data: ${JSON.stringify({ type: "thinking_done" })}\n\n`)
                );
                thinkingEnded = true;
              }
              controller.enqueue(
                encoder.encode(`data: ${JSON.stringify({ type: "text", delta: delta.content })}\n\n`)
              );
            }

            if (delta.tool_calls && Array.isArray(delta.tool_calls)) {
              if (!thinkingEnded) {
                controller.enqueue(
                  encoder.encode(`data: ${JSON.stringify({ type: "thinking_done" })}\n\n`)
                );
                thinkingEnded = true;
              }
              for (const tc of delta.tool_calls) {
                const idx = tc.index ?? 0;
                if (!toolCalls[idx]) {
                  toolCalls[idx] = {
                    id: tc.id || "",
                    name: tc.function?.name || "",
                    index: idx,
                    argsJson: "",
                  };
                  if (tc.id) {
                    controller.enqueue(
                      encoder.encode(
                        `data: ${JSON.stringify({
                          type: "tool_call_start",
                          id: tc.id,
                          name: tc.function?.name || "",
                          index: idx,
                        })}\n\n`
                      )
                    );
                  }
                }
                if (tc.function?.name) {
                  toolCalls[idx].name = tc.function.name;
                }
                if (tc.function?.arguments) {
                  toolCalls[idx].argsJson += tc.function.arguments;
                  controller.enqueue(
                    encoder.encode(
                      `data: ${JSON.stringify({
                        type: "tool_call_delta",
                        id: toolCalls[idx].id,
                        delta: tc.function.arguments,
                      })}\n\n`
                    )
                  );
                }
              }
            }
          } catch {
            // ignore parse errors for individual chunks
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    const validToolCalls = toolCalls.filter((tc) => tc && tc.id && tc.name);

    if (finishReason === "tool_calls" && validToolCalls.length > 0) {
      const assistantMsg: Record<string, unknown> = {
        role: "assistant",
        content: null,
        tool_calls: validToolCalls.map((tc) => ({
          id: tc.id,
          type: "function",
          function: {
            name: tc.name,
            arguments: tc.argsJson,
          },
        })),
      };
      currentMessages.push(assistantMsg);

      for (const tc of validToolCalls) {
        let args: Record<string, unknown> = {};
        try {
          args = tc.argsJson ? JSON.parse(tc.argsJson) : {};
        } catch {
          args = {};
        }

        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({
              type: "tool_call_end",
              id: tc.id,
              args,
            })}\n\n`
          )
        );

        const result = await executeTool(tc.name, args);

        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({
              type: "tool_result",
              id: tc.id,
              result,
            })}\n\n`
          )
        );

        const toolResultMsg: Record<string, unknown> = {
          role: "tool",
          tool_call_id: tc.id,
          content: typeof result === "string" ? result : JSON.stringify(result),
        };
        currentMessages.push(toolResultMsg);
      }
    } else {
      return;
    }
  }
}

export async function POST(request: NextRequest) {
  const abortSignal = request.signal;
  const body = await request.json();
  const { messages, temperature, maxTokens, modelPreference, tools } = body;

  const allModels = getModels();
  if (allModels.length === 0) {
    return Response.json(
      { error: "未配置任何可用的LLM模型，请检查环境变量" },
      { status: 503 }
    );
  }

  let modelsToTry: ModelConfig[];
  if (modelPreference === "primary") {
    modelsToTry = allModels.slice(0, 1);
  } else if (modelPreference === "backup1") {
    modelsToTry = allModels.slice(1, 2).length ? allModels.slice(1, 2) : allModels;
  } else if (modelPreference === "backup2") {
    modelsToTry = allModels.slice(2, 3).length ? allModels.slice(2, 3) : allModels;
  } else {
    modelsToTry = allModels;
  }

  const hasExplicitTools = "tools" in body;
  const effectiveTools = hasExplicitTools ? (tools as Record<string, unknown>[] | undefined) : [WEB_SEARCH_TOOL];
  const tempValue = typeof temperature === "number" ? temperature : 0.7;

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      let lastError = "";

      for (let i = 0; i < modelsToTry.length; i++) {
        const model = modelsToTry[i];
        const isLast = i === modelsToTry.length - 1;

        try {
          await streamWithTools(model, messages, effectiveTools, tempValue, maxTokens, encoder, controller, abortSignal);

          controller.enqueue(encoder.encode("data: [DONE]\n\n"));
          controller.close();
          return;
        } catch (error) {
          lastError = error instanceof Error ? error.message : String(error);
          if (!isLast) {
            controller.enqueue(
              encoder.encode(
                `data: ${JSON.stringify({
                  type: "fallback",
                  message: `模型 ${model.modelName} 失败，正在尝试备用模型...`,
                })}\n\n`
              )
            );
            continue;
          }
          controller.enqueue(
            encoder.encode(
              `data: ${JSON.stringify({
                type: "error",
                message: lastError,
              })}\n\n`
            )
          );
          controller.enqueue(encoder.encode("data: [DONE]\n\n"));
          controller.close();
          return;
        }
      }

      controller.enqueue(
        encoder.encode(
          `data: ${JSON.stringify({
            type: "error",
            message: lastError || "所有模型均不可用",
          })}\n\n`
        )
      );
      controller.enqueue(encoder.encode("data: [DONE]\n\n"));
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
