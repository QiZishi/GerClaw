import { generateTraceId, classifyError } from "../api-client";
import { pcm16leToWav } from "./pcm-wav";

export async function synthesizeSpeech(text: string, signal?: AbortSignal): Promise<Blob> {
  const traceId = generateTraceId();

  try {
    const response = await fetch("/api/gerclaw/voice/tts", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Trace-ID": traceId,
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

    if (!response.headers.get("content-type")?.toLowerCase().startsWith("audio/l16")) {
      throw new Error("TTS 返回的音频格式不正确");
    }
    if (response.headers.get("x-gerclaw-voice-contract") !== "voice-tts-pcm16-v1") {
      throw new Error("TTS 服务版本不兼容，请稍后重试");
    }
    return pcm16leToWav(await response.arrayBuffer());
  } catch (error) {
    if (signal?.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
    throw classifyError(error, traceId);
  }
}
