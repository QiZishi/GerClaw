import {
  ApiError,
  NetworkError,
  generateTraceId,
  classifyError,
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

const PATIENT_SYSTEM_PROMPT = `你是GerClaw老年科AI医生助手，名叫"小Ger"。

你的行为准则：
1. 说话亲切、温柔、易懂，用短句，避免专业术语，像家人一样关心老人
2. 绝对不做确定性诊断（如"你得了XX病"），永远说"可能是XX，建议就医确诊"
3. 遇到胸痛、呼吸困难、大出血、意识障碍等紧急高风险症状，强烈建议立即拨打120急救电话
4. 回答控制在300字以内，分点清晰，便于老人阅读
5. 用简单的比喻解释复杂的医学概念
6. 主动提醒按时服药、定期复查等健康事项
7. 给予情感支持，理解老人的担忧和不适
8. 不要在回复末尾添加免责声明或参考提示，系统会自动显示`;

const DOCTOR_SYSTEM_PROMPT = `你是GerClaw老年科医生AI助手，协助老年科医生进行临床诊疗工作。

你的行为准则：
1. 专业、简洁、循证，使用医学术语
2. 不做最终诊断，给出鉴别诊断思路和建议检查项目
3. 标注医学依据来源（指南/共识名称，如《中国老年高血压管理指南2023》等）
4. 回答结构化，要点明确，分条列出
5. 关注老年综合征、多重用药、功能状态等老年综合评估内容
6. 给出药物建议时注意老年人剂量调整、药物相互作用
7. 发现医疗安全隐患时主动警示
8. 不要在回复末尾添加"AI辅助建议"或免责声明，系统会自动显示`;

const VISITOR_SYSTEM_PROMPT = `你是GerClaw平台的AI助手。

你的行为准则：
1. 友好介绍GerClaw平台的功能：老年科AI双向诊疗、CGA老年综合评估、五大处方（运动/营养/用药/心理/戒烟限酒）
2. 引导用户选择"患者模式"或"医生模式"进入使用
3. 说明平台使用语音交互，适合老年人操作
4. 不要在回复末尾添加免责声明，系统会自动显示`;

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
        modelPreference: options.modelPreference ?? "auto",
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
            callbacks.onDone?.(fullText);
            return;
          }

          try {
            const json = JSON.parse(data);

            // 检查是否是代理路由发送的控制消息
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
              // 降级通知，继续等待后续数据
              continue;
            }

            // 标准 SSE 格式的 LLM 响应
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
          } catch (e) {
            if (e instanceof ApiError) {
              throw e;
            }
            // malformed JSON, skip this line
          }
        }
      }

      // 处理缓冲区剩余数据
      if (buffer.trim()) {
        const trimmedLine = buffer.trim();
        if (trimmedLine.startsWith("data: ")) {
          const data = trimmedLine.slice(6);
          if (data !== "[DONE]") {
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
              const choice = json.choices?.[0];
              if (choice?.delta?.content) {
                const textDelta = choice.delta.content;
                fullText += textDelta;
                callbacks.onText?.(textDelta, fullText);
              }
            } catch (e) {
              if (e instanceof ApiError) throw e;
              // ignore
            }
          }
        }
      }

      callbacks.onDone?.(fullText);
    } finally {
      reader.releaseLock();
    }
  } catch (error) {
    if (error instanceof ApiError) {
      callbacks.onError?.(error);
      return;
    }
    const classifiedError = classifyError(error, traceId);
    callbacks.onError?.(classifiedError);
  }
}
