import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function getApiKey(nonPublicKey: string, publicKey: string): string {
  return process.env[nonPublicKey] || process.env[publicKey] || "";
}

const PRIMARY_URL = process.env.NEXT_PUBLIC_PRIMARY_URL || "";
const PRIMARY_API_KEY = getApiKey("PRIMARY_API_KEY", "NEXT_PUBLIC_PRIMARY_API_KEY");
const PRIMARY_MODEL = process.env.NEXT_PUBLIC_PRIMARY_MODEL || "gpt-4o";

const BACKUP1_URL = process.env.NEXT_PUBLIC_BACKUP1_URL || "";
const BACKUP1_API_KEY = getApiKey("BACKUP1_API_KEY", "NEXT_PUBLIC_BACKUP1_API_KEY");
const BACKUP1_MODEL = process.env.NEXT_PUBLIC_BACKUP1_MODEL || "";

const BACKUP2_URL = process.env.NEXT_PUBLIC_BACKUP2_URL || "";
const BACKUP2_API_KEY = getApiKey("BACKUP2_API_KEY", "NEXT_PUBLIC_BACKUP2_API_KEY");
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
    description: "搜索互联网获取最新信息。仅在以下情况必须使用此工具：(1)询问最新发布的医学指南/共识/研究进展；(2)查询具体药品说明书、不良反应、最新获批适应症；(3)查询新闻事件、实时数据、医院/医生信息。对于基础医学常识、定义、正常范围、标准治疗方案、经典医学知识等你已知晓的内容，直接回答，不要搜索。注意：生成五大处方时，请优先使用local_knowledge_search检索本地知识库，本地知识库内容不足时再使用本工具。",
    parameters: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "搜索关键词，尽量精确，包含关键术语",
        },
      },
      required: ["query"],
    },
  },
};

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const LOCAL_KNOWLEDGE_SEARCH_TOOL = {
  type: "function" as const,
  function: {
    name: "local_knowledge_search",
    description: "检索本地医学知识库获取循证医学依据。知识库包含冠心病、压疮、吞咽障碍、听力障碍、便秘、失能、尿失禁、抑郁、焦虑、疼痛、睡眠障碍、肌少症、营养不良、衰弱等老年常见疾病的指南和专家共识。生成五大处方（药物/运动/营养/心理/康复）或回答上述疾病相关问题时，必须优先使用此工具获取本地权威依据，不要直接编造。",
    parameters: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "检索关键词或问题，尽量精确，包含疾病名称、药物名称、治疗方案等关键术语",
        },
        category: {
          type: "string",
          description: "可选分类过滤，如：冠心病、压疮、吞咽障碍、听力障碍、便秘、失能、尿失禁、抑郁、焦虑、疼痛、睡眠障碍、肌少症、营养不良、衰弱",
        },
      },
      required: ["query"],
    },
  },
};

const CITATION_SYSTEM_INSTRUCTION = `
【引用规范】当你使用工具获取信息后，必须严格按以下要求回答：
1. 当使用local_knowledge_search工具获取本地知识库内容时，每个引用了知识库的句子或段落末尾，使用[KB1][KB2]等角标标注本地来源序号，格式为[KB+编号]
2. 当使用web_search工具获取互联网信息时，每个引用了搜索结果的句子或段落末尾，使用[1][2]等角标标注来源序号（序号对应搜索结果的编号）
3. 角标紧跟在句号或逗号之前，放在标点前面，不要放在段落开头
4. 可以在一个句子末尾引用多个来源，如[KB1][2]
5. 不要编造不存在的角标编号，只能引用工具返回结果中实际提供的编号
6. 如果检索结果不足以回答问题，请如实说明，不要编造信息
7. 优先引用本地知识库结果，本地结果不足时再引用联网搜索结果
`;

function formatSearchResultsForLLM(result: unknown): string {
  const data = result as {
    results?: { title: string; url: string; content: string; published_date?: string }[];
    answer?: string;
    error?: string;
  };
  if (data.error) {
    return `搜索失败：${data.error}`;
  }
  const results = data.results || [];
  if (results.length === 0) {
    return "未找到相关搜索结果。";
  }
  let formatted = "";
  if (data.answer) {
    formatted += `搜索摘要：${data.answer}\n\n`;
  }
  formatted += "搜索结果（请在回答中使用[1][2]等角标引用）：\n\n";
  results.forEach((r, i) => {
    const num = i + 1;
    formatted += `[${num}] 标题：${r.title || "无标题"}\n`;
    formatted += `URL：${r.url}\n`;
    formatted += `摘要：${r.content || "无摘要"}\n`;
    if (r.published_date) {
      formatted += `发布时间：${r.published_date}\n`;
    }
    formatted += "\n";
  });
  return formatted.trim();
}

function formatLocalKnowledgeResultsForLLM(result: unknown): string {
  const data = result as {
    chunks?: Array<{ title: string; category: string; content: string }>;
    error?: string;
    total?: number;
  };
  if (data.error) {
    return `本地知识库检索失败：${data.error}`;
  }
  const chunks = data.chunks || [];
  if (chunks.length === 0) {
    return "本地知识库未找到相关内容。";
  }
  let formatted = "";
  formatted += "本地知识库检索结果（请在回答中使用[KB1][KB2]等角标引用）：\n\n";
  chunks.forEach((chunk, i) => {
    const num = i + 1;
    formatted += `[KB${num}] 标题：${chunk.title}\n`;
    formatted += `分类：${chunk.category}\n`;
    formatted += `内容：${chunk.content}\n\n`;
  });
  return formatted.trim();
}

async function executeLocalKnowledgeSearch(_query: string, _category?: string): Promise<unknown> {
  void _query;
  void _category;
  return {
    chunks: [],
    total: 0,
    source: "local_knowledge",
    message: "本地知识库功能正在维护中，请使用联网搜索",
  };
}

async function executeWebSearch(query: string): Promise<unknown> {
  const maxResults = 6;

  const medicalKeywords = /(药|医学|医疗|医院|疾病|症状|治疗|诊断|指南|处方|老年|高血压|糖尿病|冠心病|药物|保健|健康|医|症|病|痛|炎|癌|瘤|感染|手术|护理|康复|营养|运动|心理)/i;
  const isMedicalQuery = medicalKeywords.test(query);

  if (TAVILY_API_KEY) {
    try {
      const requestBody: Record<string, unknown> = {
        api_key: TAVILY_API_KEY,
        query,
        max_results: maxResults,
        include_answer: true,
      };
      if (isMedicalQuery) {
        requestBody.topic = "general";
      }
      const response = await fetch("https://api.tavily.com/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
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
  if (name === "local_knowledge_search") {
    const query = String(args.query || "");
    const category = args.category ? String(args.category) : undefined;
    if (!query) return { error: "检索关键词不能为空", chunks: [] };
    return executeLocalKnowledgeSearch(query, category);
  }
  return { error: `未知工具: ${name}` };
}

function prepareMessagesWithCitationInstruction(
  messages: Record<string, unknown>[],
  tools: Record<string, unknown>[] | undefined
): Record<string, unknown>[] {
  const hasAnyTool = tools?.some((t) => {
    const fn = (t as { function?: { name?: string } })?.function;
    return fn?.name === "web_search" || fn?.name === "local_knowledge_search";
  });
  if (!hasAnyTool) return [...messages];

  const result = [...messages];
  const sysIdx = result.findIndex((m) => (m as { role?: string }).role === "system");
  if (sysIdx !== -1) {
    const sysMsg = result[sysIdx] as { role: string; content: string | unknown };
    const existingContent = typeof sysMsg.content === "string" ? sysMsg.content : "";
    if (!existingContent.includes("【引用规范】")) {
      result[sysIdx] = {
        ...sysMsg,
        content: existingContent + CITATION_SYSTEM_INSTRUCTION,
      };
    }
  } else {
    result.unshift({
      role: "system",
      content: CITATION_SYSTEM_INSTRUCTION.trim(),
    });
  }
  return result;
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
  const currentMessages = prepareMessagesWithCitationInstruction(messages, tools);
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

        let toolContent: string;
        if (tc.name === "web_search") {
          toolContent = formatSearchResultsForLLM(result);
        } else if (tc.name === "local_knowledge_search") {
          toolContent = formatLocalKnowledgeResultsForLLM(result);
        } else {
          toolContent = typeof result === "string" ? result : JSON.stringify(result);
        }
        const toolResultMsg: Record<string, unknown> = {
          role: "tool",
          tool_call_id: tc.id,
          content: toolContent,
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
