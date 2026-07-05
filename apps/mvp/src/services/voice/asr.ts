import { generateTraceId, classifyError } from "../api-client";

function blobToBase64DataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
      } else {
        reject(new Error("Failed to convert blob to base64"));
      }
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

export async function recognizeAudio(audioBlob: Blob): Promise<string> {
  const traceId = generateTraceId();

  try {
    const base64DataUrl = await blobToBase64DataUrl(audioBlob);

    const response = await fetch("/api/voice/asr", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Trace-Id": traceId,
      },
      body: JSON.stringify({
        audio: base64DataUrl,
        language: "auto",
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
