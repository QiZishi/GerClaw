import { primaryModel, backup1Model, backup2Model } from "@/lib/config";
import {
  ApiError,
  NetworkError,
  TimeoutError,
  RateLimitError,
  AuthenticationError,
  ServerError,
  generateTraceId,
  fetchWithTimeout,
  classifyError,
  classifyHttpError,
} from "../api-client";

export interface LLMMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface LLMStreamCallbacks {
  onText?: (delta: string, fullText: string) => void;
  onThinking?: (delta: string) => void;
  onDone?: (fullText: string) => void;
  onError?: (error: Error) => void;
}

export interface StreamOptions {
  temperature?: number;
  maxTokens?: number;
  signal?: AbortSignal;
  modelPreference?: "primary" | "backup1" | "backup2" | "auto";
}

interface ModelConfig {
  url: string;
  apiKey: string;
  modelName: string;
  protocol: string;
  preference: "primary" | "backup1" | "backup2";
}

const PATIENT_SYSTEM_PROMPT = `你是GerClaw老年科AI医生助手，名叫"小Ger"。

你的行为准则：
1. 说话亲切、温柔、易懂，用短句，避免专业术语，像家人一样关心老人
2. 绝对不做确定性诊断（如"你得了XX病"），永远说"可能是XX，建议就医确诊"
3. 遇到胸痛、呼吸困难、大出血、意识障碍等紧急高风险症状，强烈建议立即拨打120急救电话
4. 每次回复结尾自然带上"以上建议仅供参考，身体不适请及时就医"
5. 回答控制在300字以内，分点清晰，便于老人阅读
6. 用简单的比喻解释复杂的医学概念
7. 主动提醒按时服药、定期复查等健康事项
8. 给予情感支持，理解老人的担忧和不适`;

const DOCTOR_SYSTEM_PROMPT = `你是GerClaw老年科医生AI助手，协助老年科医生进行临床诊疗工作。

你的行为准则：
1. 专业、简洁、循证，使用医学术语
2. 不做最终诊断，给出鉴别诊断思路和建议检查项目
3. 标注医学依据来源（指南/共识名称，如《中国老年高血压管理指南2023》等）
4. 回答结构化，要点明确，分条列出
5. 关注老年综合征、多重用药、功能状态等老年综合评估内容
6. 给出药物建议时注意老年人剂量调整、药物相互作用
7. 结尾标注"AI辅助建议，需结合临床判断"
8. 发现医疗安全隐患时主动警示`;

const VISITOR_SYSTEM_PROMPT = `你是GerClaw平台的AI助手。

你的行为准则：
1. 友好介绍GerClaw平台的功能：老年科AI双向诊疗、CGA老年综合评估、五大处方（运动/营养/用药/心理/戒烟限酒）
2. 引导用户选择"患者模式"或"医生模式"进入使用
3. 说明平台使用语音交互，适合老年人操作
4. 提醒本平台仅供健康咨询参考，不能替代线下就医
5. 结尾标注"以上建议仅供参考，身体不适请及时就医"`;

export function buildSystemPrompt(role: "patient" | "doctor" | "visitor"): string {
  switch (role) {
    case "patient":
      return PATIENT_SYSTEM_PROMPT;
    case "doctor":
      return DOCTOR_SYSTEM_PROMPT;
    case "visitor":
      return VISITOR_SYSTEM_PROMPT;
  }
}

function getModelList(modelPreference: StreamOptions["modelPreference"]): ModelConfig[] {
  switch (modelPreference) {
    case "primary":
      return [primaryModel];
    case "backup1":
      return [backup1Model];
    case "backup2":
      return [backup2Model];
    case "auto":
    default:
      return [primaryModel, backup1Model, backup2Model];
  }
}

function buildChatUrl(baseUrl: string): string {
  const trimmedUrl = baseUrl.replace(/\/+$/, "");
  if (trimmedUrl.endsWith("/chat/completions")) {
    return trimmedUrl;
  }
  if (trimmedUrl.endsWith("/v1")) {
    return `${trimmedUrl}/chat/completions`;
  }
  if (trimmedUrl.includes("/compatible-mode")) {
    return `${trimmedUrl}/chat/completions`;
  }
  if (trimmedUrl.includes("/api/v1")) {
    return `${trimmedUrl}/chat/completions`;
  }
  return `${trimmedUrl}/chat/completions`;
}

async function streamWithModel(
  model: ModelConfig,
  messages: LLMMessage[],
  options: StreamOptions,
  callbacks: LLMStreamCallbacks,
  traceId: string
): Promise<string> {
  const url = buildChatUrl(model.url);
  const temperature = options.temperature ?? 0.7;
  const maxTokens = options.maxTokens;

  const body: Record<string, unknown> = {
    model: model.modelName,
    messages,
    stream: true,
    temperature,
  };

  if (maxTokens) {
    body.max_tokens = maxTokens;
  }

  const response = await fetchWithTimeout(
    url,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${model.apiKey}`,
      },
      body: JSON.stringify(body),
      signal: options.signal,
      timeoutMs: 60000,
    },
    60000
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

  if (!response.body) {
    throw new ApiError("响应体为空", "EMPTY_RESPONSE", undefined, false, traceId);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let fullText = "";
  let buffer = "";

  try {
    while (true) {
      if (options.signal?.aborted) {
        throw new ApiError("请求已取消", "ABORTED", undefined, false, traceId);
      }

      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmedLine = line.trim();
        if (!trimmedLine) continue;
        if (!trimmedLine.startsWith("data: ")) continue;

        const data = trimmedLine.slice(6);
        if (data === "[DONE]") {
          return fullText;
        }

        try {
          const json = JSON.parse(data);
          const choice = json.choices?.[0];
          if (!choice) continue;

          const delta = choice.delta;
          if (!delta) continue;

          if (delta.reasoning_content) {
            callbacks.onThinking?.(delta.reasoning_content);
          }

          if (delta.content) {
            const textDelta = delta.content;
            fullText += textDelta;
            callbacks.onText?.(textDelta, fullText);
          }
        } catch {
          // malformed JSON, skip this line
        }
      }
    }

    if (buffer.trim()) {
      const trimmedLine = buffer.trim();
      if (trimmedLine.startsWith("data: ")) {
        const data = trimmedLine.slice(6);
        if (data !== "[DONE]") {
          try {
            const json = JSON.parse(data);
            const choice = json.choices?.[0];
            if (choice?.delta?.content) {
              const textDelta = choice.delta.content;
              fullText += textDelta;
              callbacks.onText?.(textDelta, fullText);
            }
          } catch {
            // ignore
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  return fullText;
}

function isFallbackableError(error: unknown): boolean {
  if (error instanceof NetworkError) return true;
  if (error instanceof TimeoutError) return true;
  if (error instanceof RateLimitError) return true;
  if (error instanceof ServerError) return true;
  if (error instanceof AuthenticationError) return false;
  if (error instanceof ApiError && error.retriable) return true;
  return false;
}

export async function streamChat(
  messages: LLMMessage[],
  options: StreamOptions,
  callbacks: LLMStreamCallbacks
): Promise<void> {
  const traceId = generateTraceId();
  const modelList = getModelList(options.modelPreference ?? "auto");
  const availableModels = modelList.filter((m) => m.url && m.apiKey);

  if (availableModels.length === 0) {
    const error = new ApiError(
      "未配置任何可用的LLM模型，请检查环境变量",
      "NO_MODEL_CONFIGURED",
      undefined,
      false,
      traceId
    );
    callbacks.onError?.(error);
    return;
  }

  let lastError: unknown = null;

  for (let i = 0; i < availableModels.length; i++) {
    const model = availableModels[i];
    const isLastModel = i === availableModels.length - 1;

    try {
      const fullText = await streamWithModel(
        model,
        messages,
        options,
        callbacks,
        traceId
      );
      callbacks.onDone?.(fullText);
      return;
    } catch (error) {
      lastError = error;

      if (!isLastModel && isFallbackableError(error)) {
        continue;
      }

      if (isLastModel || !isFallbackableError(error)) {
        const classifiedError = classifyError(error, traceId);
        callbacks.onError?.(classifiedError);
        return;
      }
    }
  }

  if (lastError) {
    const classifiedError = classifyError(lastError, traceId);
    callbacks.onError?.(classifiedError);
  }
}
