import { generateTraceId, classifyError } from "../api-client";

export async function synthesizeSpeech(text: string, signal?: AbortSignal): Promise<Blob> {
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

    const blob = await response.blob();
    if (blob.size === 0) {
      throw new Error("TTS 返回音频为空");
    }

    return blob;
  } catch (error) {
    if (signal?.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
    throw classifyError(error, traceId);
  }
}
