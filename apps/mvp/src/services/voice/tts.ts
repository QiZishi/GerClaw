import { generateTraceId, classifyError } from "../api-client";

interface TTSCallbacks {
  onAudioChunk?: (pcm: Int16Array) => void;
  onDone?: () => void;
  onError?: (err: Error) => void;
}

function base64ToInt16Array(base64: string): Int16Array {
  const binaryString = atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return new Int16Array(bytes.buffer);
}

export async function streamTTS(
  text: string,
  callbacks: TTSCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const traceId = generateTraceId();

  try {
    const response = await fetch("/api/voice/tts", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Trace-Id": traceId,
      },
      body: JSON.stringify({ text }),
      signal,
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
      throw new Error(errorMessage);
    }

    if (!response.body) {
      throw new Error("TTS 响应体为空");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        if (signal?.aborted) {
          return;
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
            callbacks.onDone?.();
            return;
          }

          try {
            const json = JSON.parse(data);

            // 检查代理路由错误消息
            if (json.type === "error") {
              throw new Error(json.message || "TTS 服务错误");
            }

            const choice = json.choices?.[0];
            if (!choice) continue;

            const delta = choice.delta;
            if (!delta) continue;

            const audioData = delta.audio?.data;
            if (audioData && typeof audioData === "string") {
              const pcmData = base64ToInt16Array(audioData);
              callbacks.onAudioChunk?.(pcmData);
            }
          } catch (e) {
            if (e instanceof Error && e.message.includes("TTS 服务错误")) {
              throw e;
            }
            // malformed JSON, skip
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
              if (json.type === "error") {
                throw new Error(json.message || "TTS 服务错误");
              }
              const choice = json.choices?.[0];
              const audioData = choice?.delta?.audio?.data;
              if (audioData && typeof audioData === "string") {
                const pcmData = base64ToInt16Array(audioData);
                callbacks.onAudioChunk?.(pcmData);
              }
            } catch (e) {
              if (e instanceof Error && e.message.includes("TTS 服务错误")) {
                throw e;
              }
              // ignore
            }
          }
        }
      }

      callbacks.onDone?.();
    } finally {
      reader.releaseLock();
    }
  } catch (error) {
    if (signal?.aborted) {
      return;
    }
    const classifiedError = classifyError(error, traceId);
    callbacks.onError?.(classifiedError);
  }
}
