import { NextRequest } from "next/server";
import { z } from "zod";
import { API_TIMEOUT } from "@/lib/constants";
import { getVoiceProvider, mimoAuthorizationHeaders } from "@/server/voice-provider";
import {
  parseTtsRequest,
  takeVoiceRequestSlot,
  voiceErrorResponse,
} from "@/server/voice-request";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ttsResponseSchema = z.object({
  choices: z.array(
    z.object({
      message: z.object({
        audio: z.object({
          data: z.string().min(1).max(24 * 1024 * 1024).regex(/^[A-Za-z0-9+/]+={0,2}$/),
        }).passthrough(),
      }).passthrough(),
    }).passthrough()
  ).min(1),
}).passthrough();

export async function POST(request: NextRequest) {
  try {
    takeVoiceRequestSlot(request);
    // A complete assistant reply can take longer than a short voice check to
    // synthesize. Use the shared TTS deadline and keep the client abort signal
    // in the race so “正在准备，点击取消” always stops the upstream request.
    const operationSignal = AbortSignal.any([request.signal, AbortSignal.timeout(API_TIMEOUT.tts)]);
    const { text, voice } = await parseTtsRequest(request, operationSignal);
    const { url: ttsUrl, apiKey: ttsApiKey, model: ttsModel, voice: ttsVoice } = getVoiceProvider("tts");
    if (!ttsUrl || !ttsApiKey) {
      return Response.json({ error: "语音合成服务暂时不可用。" }, { status: 503 });
    }

    const url = ttsUrl.replace(/\/+$/, "") + "/chat/completions";

    const requestBody: Record<string, unknown> = {
      model: ttsModel,
      messages: [
        {
          role: "assistant",
          content: text,
        },
      ],
      audio: {
        format: "wav",
        voice: voice || ttsVoice,
      },
      stream: false,
    };

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...mimoAuthorizationHeaders(ttsApiKey),
      },
      body: JSON.stringify(requestBody),
      signal: operationSignal,
    });

    if (!response.ok) {
      return Response.json({ error: "语音合成服务暂时不可用，请稍后重试。" }, { status: 502 });
    }

    const parsedResponse = ttsResponseSchema.safeParse(await response.json().catch(() => null));
    if (!parsedResponse.success) {
      return Response.json(
        { error: "TTS 响应格式异常，未获取到音频数据" },
        { status: 502 }
      );
    }
    const audioBase64 = parsedResponse.data.choices[0].message.audio.data;

    const audioBuffer = Buffer.from(audioBase64, "base64");

    return new Response(audioBuffer, {
      headers: {
        "Content-Type": "audio/wav",
        "Content-Length": audioBuffer.length.toString(),
        "Cache-Control": "no-cache",
      },
    });
  } catch (error) {
    return voiceErrorResponse(error);
  }
}
