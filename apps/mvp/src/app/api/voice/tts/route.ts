import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const TTS_URL = process.env.NEXT_PUBLIC_TTS_URL || "";
const TTS_API_KEY = process.env.NEXT_PUBLIC_TTS_API_KEY || "";
const TTS_MODEL = process.env.NEXT_PUBLIC_TTS_MODEL || "mimo-v2.5-tts";
const TTS_VOICE = process.env.NEXT_PUBLIC_TTS_VOICE || "冰糖";

export async function POST(request: NextRequest) {
  if (!TTS_URL || !TTS_API_KEY) {
    return Response.json(
      { error: "TTS 服务未配置，请检查环境变量" },
      { status: 503 }
    );
  }

  try {
    const body = await request.json();
    const { text, voice, model } = body;

    const url = TTS_URL.replace(/\/+$/, "") + "/chat/completions";

    const requestBody: Record<string, unknown> = {
      model: model || TTS_MODEL,
      messages: [
        {
          role: "user",
          content: "用温柔体贴的语调，语速适中，像在关心一位老人的健康状况",
        },
        {
          role: "assistant",
          content: text,
        },
      ],
      audio: {
        format: "pcm16",
        voice: voice || TTS_VOICE,
      },
      stream: true,
    };

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${TTS_API_KEY}`,
        "api-key": TTS_API_KEY,
      },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const errText = await response.text();
      return Response.json(
        { error: `TTS 请求失败: HTTP ${response.status} ${errText}` },
        { status: response.status }
      );
    }

    if (!response.body) {
      return Response.json(
        { error: "TTS 响应体为空" },
        { status: 502 }
      );
    }

    const encoder = new TextEncoder();

    const stream = new ReadableStream({
      async start(controller) {
        const reader = response.body!.getReader();
        const decoder = new TextDecoder();

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value, { stream: true });
            controller.enqueue(encoder.encode(text));
          }
        } finally {
          reader.releaseLock();
        }

        controller.enqueue(encoder.encode("data: [DONE]\n\n"));
        controller.close();
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return Response.json(
      { error: `TTS 服务异常: ${message}` },
      { status: 500 }
    );
  }
}
