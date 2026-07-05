import { voiceConfig } from "@/lib/config";
import {
  generateTraceId,
  fetchWithTimeout,
  classifyError,
  classifyHttpError,
} from "../api-client";

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

  if (!voiceConfig.asrUrl || !voiceConfig.asrApiKey) {
    throw new Error("ASR 服务未配置，请检查环境变量");
  }

  try {
    const base64DataUrl = await blobToBase64DataUrl(audioBlob);

    const url = voiceConfig.asrUrl.replace(/\/+$/, "") + "/chat/completions";

    const body = {
      model: voiceConfig.asrModel,
      messages: [
        {
          role: "user",
          content: [
            {
              type: "input_audio",
              input_audio: {
                data: base64DataUrl,
              },
            },
          ],
        },
      ],
      asr_options: {
        language: "auto",
      },
      stream: false,
    };

    const response = await fetchWithTimeout(
      url,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "api-key": voiceConfig.asrApiKey,
        },
        body: JSON.stringify(body),
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

    const json = await response.json();
    const text = json?.choices?.[0]?.message?.content;

    if (typeof text !== "string") {
      throw new Error("ASR 响应格式异常，未获取到识别文本");
    }

    return text.trim();
  } catch (error) {
    throw classifyError(error, traceId);
  }
}
