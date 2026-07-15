import { NextRequest } from "next/server";
import { z } from "zod";
import { getVoiceProvider, mimoAuthorizationHeaders } from "@/server/voice-provider";
import {
  parseAsrRequest,
  takeVoiceRequestSlot,
  voiceErrorResponse,
} from "@/server/voice-request";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const asrResponseSchema = z.object({
  choices: z.array(
    z.object({
      message: z.object({ content: z.string().max(4_000) }).passthrough(),
    }).passthrough()
  ).min(1),
}).passthrough();

export async function POST(request: NextRequest) {
  try {
    takeVoiceRequestSlot(request);
    const operationSignal = AbortSignal.any([request.signal, AbortSignal.timeout(30_000)]);
    const { audio, format } = await parseAsrRequest(request, operationSignal);
    const { url: asrUrl, apiKey: asrApiKey, model: asrModel } = getVoiceProvider("asr");
    if (!asrUrl || !asrApiKey) {
      return Response.json({ error: "语音识别服务暂时不可用，请改用文字输入。" }, { status: 503 });
    }

    const url = asrUrl.replace(/\/+$/, "") + "/chat/completions";

    const requestBody: Record<string, unknown> = {
      model: asrModel,
      messages: [
        {
          role: "user",
          content: [
            {
              type: "input_audio",
              input_audio: {
                data: audio,
                format,
              },
            },
          ],
        },
      ],
      stream: false,
    };

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...mimoAuthorizationHeaders(asrApiKey),
      },
      body: JSON.stringify(requestBody),
      signal: operationSignal,
    });

    if (!response.ok) {
      return Response.json({ error: "语音识别服务暂时不可用，请改用文字输入。" }, { status: 502 });
    }

    const parsedResponse = asrResponseSchema.safeParse(await response.json().catch(() => null));
    if (!parsedResponse.success) {
      return Response.json(
        { error: "ASR 响应格式异常，未获取到识别文本" },
        { status: 502 }
      );
    }
    const text = parsedResponse.data.choices[0].message.content;

    const trimmed = text.trim();
    if (!trimmed) return Response.json({ error: "未能识别到语音内容，请重新说话或改用文字输入。" }, { status: 422 });
    return Response.json({ text: trimmed });
  } catch (error) {
    return voiceErrorResponse(error);
  }
}
