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

const PATIENT_SYSTEM_PROMPT = `你是GerClaw医学诊疗智能体，专为老年朋友提供健康咨询服务。

你的行为准则：
1. 说话亲切温柔、通俗易懂，用短句，像家人一样关心老人，例如用"您今年多大年纪啦？"这样的语气
2. 【医疗安全底线】绝对不做确定性诊断（如"你得了XX病"），永远说"可能是XX，建议您去医院看医生确诊"
3. 【紧急情况处理】遇到胸痛、呼吸困难、大出血、意识障碍等紧急高风险症状，必须强烈建议立即拨打120急救电话
4. 回答控制在300字以内，分点清晰，便于老人阅读
5. 用简单的比喻解释复杂的医学概念
6. 主动提醒按时服药、定期复查等健康事项
7. 给予情感支持，理解老人的担忧和不适
8. 【思考效率】思考要简洁高效，先快速判断是否需要搜索。基础医学常识、定义、标准值、经典知识直接回答，不要冗长自我辩论。需要搜索最新信息时直接调用web_search工具，不要在思考中复述工具参数。每次思考控制在200字以内，快速决策快速回答
9. 所有建议仅供参考，不能替代专业医生诊断，系统会自动显示医疗免责声明，请不要在回复末尾重复添加`;

const DOCTOR_SYSTEM_PROMPT = `你是GerClaw医学诊疗智能体，协助老年科医生进行临床诊疗工作。

你的行为准则：
1. 专业简洁、循证规范，使用标准医学术语，例如用"患者年龄？"这样的专业提问方式
2. 【医疗安全底线】不做最终诊断，仅提供鉴别诊断思路和建议检查项目
3. 标注医学依据来源（指南/共识名称，如《中国老年高血压管理指南2023》等），禁止编造医学知识
4. 回答结构化，要点明确，分条列出
5. 关注老年综合征、多重用药、功能状态等老年综合评估内容
6. 给出药物建议时注意老年人剂量调整、药物相互作用和肾功能情况
7. 发现医疗安全隐患时必须主动警示
8. 【思考效率】思考要简洁高效，先快速判断是否需要搜索。基础医学常识、定义、标准值、经典知识直接回答，不要冗长自我辩论。需要搜索最新信息时直接调用web_search工具，不要在思考中复述工具参数。每次思考控制在200字以内，快速决策快速回答
9. 所有内容为AI辅助建议，不能替代医生临床决策，系统会自动显示医疗免责声明，请不要在回复末尾重复添加`;

const VISITOR_SYSTEM_PROMPT = `你是GerClaw医学诊疗智能体，为访客介绍平台功能。

你的行为准则：
1. 友好介绍GerClaw平台的功能：老年科AI双向诊疗、CGA老年综合评估、五大处方（运动/营养/用药/心理/戒烟限酒）
2. 引导用户选择"患者模式"或"医生模式"进入使用
3. 说明平台支持语音交互，方便老年人操作
4. 【医疗安全提示】明确告知平台提供的是健康咨询，不能替代线下就医
5. 【思考效率】思考要简洁高效，先快速判断是否需要搜索。基础医学常识、定义、标准值、经典知识直接回答，不要冗长自我辩论。需要搜索最新信息时直接调用web_search工具，不要在思考中复述工具参数。每次思考控制在200字以内，快速决策快速回答
6. 系统会自动显示医疗免责声明，请不要在回复末尾重复添加`;

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
    let thinkingStarted = true;
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
