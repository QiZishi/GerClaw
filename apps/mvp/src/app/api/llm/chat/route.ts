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

interface ModelConfig {
  url: string;
  apiKey: string;
  modelName: string;
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

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { messages, temperature, maxTokens, modelPreference } = body;

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

  const requestHeaders: Record<string, string> = {
    "Content-Type": "application/json",
  };

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      let lastError = "";

      for (let i = 0; i < modelsToTry.length; i++) {
        const model = modelsToTry[i];
        const isLast = i === modelsToTry.length - 1;

        try {
          const url = buildChatUrl(model.url);
          const reqBody: Record<string, unknown> = {
            model: model.modelName,
            messages,
            stream: true,
            temperature: temperature ?? 0.7,
            enable_thinking: false,
          };
          if (maxTokens) {
            reqBody.max_tokens = maxTokens;
          }

          const response = await fetch(url, {
            method: "POST",
            headers: {
              ...requestHeaders,
              Authorization: `Bearer ${model.apiKey}`,
            },
            body: JSON.stringify(reqBody),
          });

          if (!response.ok) {
            const errText = await response.text();
            lastError = `HTTP ${response.status}: ${errText}`;
            if (!isLast && response.status >= 500) {
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
            if (!isLast && response.status === 429) {
              controller.enqueue(
                encoder.encode(
                  `data: ${JSON.stringify({
                    type: "fallback",
                    message: `模型 ${model.modelName} 限流，正在尝试备用模型...`,
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

          if (!response.body) {
            lastError = "响应体为空";
            if (!isLast) continue;
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

          const reader = response.body.getReader();
          const decoder = new TextDecoder();

          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;

              const text = decoder.decode(value, { stream: true });
              controller.enqueue(encoder.encode(text));
            }
          } finally {
            reader.releaseLock();
          }

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
                  message: `模型 ${model.modelName} 异常，正在尝试备用模型...`,
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
