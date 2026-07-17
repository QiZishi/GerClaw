import { generateTraceId, classifyError } from "../api-client";
import { convertBlobToWavBase64 } from "./audio-convert";

function throwIfAborted(signal?: AbortSignal) {
  if (signal?.aborted) {
    throw signal.reason ?? new DOMException("语音识别已取消", "AbortError");
  }
}

export async function recognizeAudio(audioBlob: Blob, signal?: AbortSignal): Promise<string> {
  const traceId = generateTraceId();

  try {
    throwIfAborted(signal);
    const { base64: wavBase64 } = await convertBlobToWavBase64(audioBlob);
    throwIfAborted(signal);

    const response = await fetch("/api/gerclaw/voice/asr", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Trace-ID": traceId,
      },
      body: JSON.stringify({
        audio: wavBase64,
        format: "wav",
      }),
      signal,
    });

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}`;
      try {
        const errorBody = await response.text();
        if (errorBody) {
          try {
            const errorJson = JSON.parse(errorBody);
            errorMessage = errorJson.error || errorJson.detail?.message || errorMessage;
          } catch {
            errorMessage = errorBody;
          }
        }
      } catch {
        // ignore
      }
      throw new Error(errorMessage);
    }

    const json = await response.json();

    const text = json.text;

    if (typeof text !== "string") {
      throw new Error("ASR 响应格式异常，未获取到识别文本");
    }

    return text.trim();
  } catch (error) {
    if (signal?.aborted) {
      throw signal.reason ?? new DOMException("语音识别已取消", "AbortError");
    }
    throw classifyError(error, traceId);
  }
}
