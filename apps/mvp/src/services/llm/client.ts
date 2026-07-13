import {
  ApiError,
  NetworkError,
  generateTraceId,
  classifyError,
} from "../api-client";
import { mapFrontendToBackend, type FrontendModelId, type BackendModelId } from "@/config/models";

export interface LLMTool {
  type: "function";
  function: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  };
}

export interface LLMMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string | LLMContentPart[] | null;
  tool_calls?: LLMToolCall[];
  tool_call_id?: string;
}

export type LLMContentPart =
  | { type: "text"; text: string }
  | { type: "image_url"; image_url: { url: string } };

export interface LLMToolCall {
  id: string;
  type: "function";
  function: {
    name: string;
    arguments: string;
  };
  index?: number;
}

export interface LLMStreamCallbacks {
  onText?: (delta: string, fullText: string) => void;
  onThinkingDelta?: (delta: string, fullThinking: string) => void;
  onThinkingStart?: () => void;
  onThinkingDone?: (fullThinking: string) => void;
  onToolCallStart?: (toolCall: { id: string; name: string; index: number }) => void;
  onToolCallDelta?: (toolCallId: string, delta: string) => void;
  onToolCallEnd?: (toolCallId: string, args: Record<string, unknown>) => void;
  onToolResult?: (toolCallId: string, result: unknown) => void;
  onFallback?: (message: string) => void;
  onDone?: (fullText: string) => void;
  onError?: (error: Error) => void;
}

export interface StreamOptions {
  temperature?: number;
  maxTokens?: number;
  signal?: AbortSignal;
  modelPreference?: FrontendModelId | BackendModelId;
  tools?: LLMTool[];
}

const PATIENT_SYSTEM_PROMPT = `你是GerClaw老年医学AI助手，用亲切通俗的语言回答老年健康问题。

核心规则：
1. 语气温暖耐心，用短句和简单比喻，像家人一样沟通
2. 禁止确定性诊断，建议就医确诊
3. 胸痛/呼吸困难/大出血/意识障碍等急症须立即建议拨打120
4. 回答简洁（300字内），分点清晰
5. 主动提醒用药和复查
6. 思考要快：常识直接回答，需最新信息才搜索，不要冗长推理，每次思考不超过200字
7. 系统自动附免责声明，不要重复添加`;

const DOCTOR_SYSTEM_PROMPT = `你是GerClaw老年科AI助手，协助医生进行老年患者诊疗。

核心规则：
1. 专业简洁，使用标准医学术语，循证规范
2. 不做最终诊断，提供鉴别诊断和检查建议
3. 标注依据来源（指南/共识名称），禁止编造
4. 结构化输出，重点关注老年综合征、多重用药、功能状态
5. 注意老年人剂量调整、药物相互作用和肾功能
6. 发现安全隐患主动警示
7. 思考要快：常识直接回答，需最新信息才搜索，不要冗长推理，每次思考不超过200字
8. 系统自动附免责声明，不要重复添加`;

const VISITOR_SYSTEM_PROMPT = `你是GerClaw平台引导助手，为访客介绍平台功能。

核心规则：
1. 介绍GerClaw三大功能：老年科AI诊疗、CGA老年综合评估、五大处方（运动/营养/用药/心理/戒烟限酒）
2. 引导用户选择患者或医生模式
3. 说明支持语音交互，适合老年人操作
4. 明确告知平台提供健康咨询，不能替代线下就医
5. 思考要快：直接回答，不要冗长推理
6. 系统自动附免责声明，不要重复添加`;

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

export async function streamChat(
  messages: LLMMessage[],
  options: StreamOptions,
  callbacks: LLMStreamCallbacks
): Promise<void> {
  const traceId = generateTraceId();

  const rawModelPref = options.modelPreference ?? "auto";
  const backendModelPref: BackendModelId = (["primary", "backup1", "backup2", "auto"] as const).includes(
    rawModelPref as BackendModelId
  )
    ? (rawModelPref as BackendModelId)
    : mapFrontendToBackend(rawModelPref as FrontendModelId);

  try {
    const response = await fetch("/api/llm/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Trace-Id": traceId,
      },
      body: JSON.stringify({
        messages,
        temperature: options.temperature ?? 0.7,
        maxTokens: options.maxTokens,
        modelPreference: backendModelPref,
        tools: options.tools,
      }),
      signal: options.signal,
    });

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}`;
      try {
        const errorBody = await response.text();
        if (errorBody) {
          try {
            const errorJson = JSON.parse(errorBody);
            errorMessage = errorJson.error || errorMessage;
          } catch {
            errorMessage = errorBody;
          }
        }
      } catch {
        // ignore
      }
      throw classifyError(new Error(errorMessage), traceId);
    }

    if (!response.body) {
      throw new NetworkError("响应体为空", traceId);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let fullText = "";
    let fullThinking = "";
    let buffer = "";
    let thinkingStarted = false;
    let thinkingEnded = false;

    const finishCurrentThinking = () => {
      if (thinkingStarted && !thinkingEnded) {
        callbacks.onThinkingDone?.(fullThinking);
        thinkingEnded = true;
      }
    };

    const startNewThinking = () => {
      if (!thinkingStarted || thinkingEnded) {
        fullThinking = "";
        thinkingStarted = true;
        thinkingEnded = false;
        callbacks.onThinkingStart?.();
      }
    };

    const processSSELine = (line: string): boolean => {
      const trimmedLine = line.trim();
      if (!trimmedLine) return true;
      if (!trimmedLine.startsWith("data: ")) return true;

      const data = trimmedLine.slice(6);
      if (data === "[DONE]") {
        finishCurrentThinking();
        callbacks.onDone?.(fullText);
        return false;
      }

      try {
        const json = JSON.parse(data);

        if (json.type === "error") {
          throw new ApiError(
            json.message || "LLM 服务错误",
            "LLM_ERROR",
            undefined,
            false,
            traceId
          );
        }
        if (json.type === "fallback") {
          callbacks.onFallback?.(json.message || "正在切换备用模型...");
          return true;
        }

        if (json.type === "text" && json.delta) {
          finishCurrentThinking();
          const textDelta = json.delta;
          fullText += textDelta;
          callbacks.onText?.(textDelta, fullText);
          return true;
        }

        if (json.type === "thinking_start") {
          startNewThinking();
          return true;
        }

        if (json.type === "thinking" && json.delta) {
          if (thinkingEnded) {
            startNewThinking();
          } else if (!thinkingStarted) {
            startNewThinking();
          }
          fullThinking += json.delta;
          callbacks.onThinkingDelta?.(json.delta, fullThinking);
          return true;
        }

        if (json.type === "thinking_done") {
          finishCurrentThinking();
          return true;
        }

        if (json.type === "tool_call_start") {
          finishCurrentThinking();
          callbacks.onToolCallStart?.({
            id: json.id,
            name: json.name,
            index: json.index ?? 0,
          });
          return true;
        }

        if (json.type === "tool_call_delta") {
          callbacks.onToolCallDelta?.(json.id, json.delta ?? "");
          return true;
        }

        if (json.type === "tool_call_end") {
          let args: Record<string, unknown> = {};
          if (json.args) {
            try {
              args = typeof json.args === "string" ? JSON.parse(json.args) : json.args;
            } catch {
              args = {};
            }
          }
          callbacks.onToolCallEnd?.(json.id, args);
          return true;
        }

        if (json.type === "tool_result") {
          callbacks.onToolResult?.(json.id, json.result);
          return true;
        }

        const choice = json.choices?.[0];
        if (!choice) return true;

        const delta = choice.delta;
        if (!delta) return true;

        const thinkingDelta = delta.reasoning_content || delta.thinking;
        if (thinkingDelta) {
          if (thinkingEnded) {
            startNewThinking();
          } else if (!thinkingStarted) {
            startNewThinking();
          }
          fullThinking += thinkingDelta;
          callbacks.onThinkingDelta?.(thinkingDelta, fullThinking);
        }

        if (delta.content) {
          finishCurrentThinking();
          const textDelta = delta.content;
          fullText += textDelta;
          callbacks.onText?.(textDelta, fullText);
        }
      } catch (e) {
        if (e instanceof ApiError) {
          throw e;
        }
      }
      return true;
    };

    try {
      while (true) {
        let readResult;
        try {
          readResult = await reader.read();
        } catch (readError) {
          if (
            readError instanceof Error &&
            (readError.name === "AbortError" || options.signal?.aborted)
          ) {
            return;
          }
          if (fullText) {
            callbacks.onDone?.(fullText);
          } else {
            throw readError;
          }
          return;
        }

        const { done, value } = readResult;
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!processSSELine(line)) {
            return;
          }
        }
      }

      if (buffer.trim()) {
        processSSELine(buffer);
      }

      callbacks.onDone?.(fullText);
    } finally {
      try {
        reader.releaseLock();
      } catch {
        // ignore
      }
    }
  } catch (error) {
    if (
      error instanceof Error &&
      (error.name === "AbortError" || options.signal?.aborted)
    ) {
      return;
    }
    if (error instanceof ApiError) {
      callbacks.onError?.(error);
      return;
    }
    const classifiedError = classifyError(error, traceId);
    callbacks.onError?.(classifiedError);
  }
}
