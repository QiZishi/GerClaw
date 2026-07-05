import { generateTraceId, classifyError } from "../api-client";
import { convertBlobToWavBase64 } from "./audio-convert";

export async function recognizeAudio(audioBlob: Blob): Promise<string> {
  const traceId = generateTraceId();

  try {
    const { base64: wavBase64 } = await convertBlobToWavBase64(audioBlob);

    const response = await fetch("/api/voice/asr", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Trace-Id": traceId,
      },
      body: JSON.stringify({
        audio: wavBase64,
        format: "wav",
      }),
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

    const json = await response.json();

    if (json.error) {
      throw new Error(json.error);
    }

    const text = json.text;

    if (typeof text !== "string") {
      throw new Error("ASR 响应格式异常，未获取到识别文本");
    }

    return text.trim();
  } catch (error) {
    throw classifyError(error, traceId);
  }
}
