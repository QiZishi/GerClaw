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
    const { text, voice } = body;

    if (!text || typeof text !== "string") {
      return Response.json(
        { error: "缺少要合成的文本" },
        { status: 400 }
      );
    }

    const url = TTS_URL.replace(/\/+$/, "") + "/chat/completions";

    const requestBody: Record<string, unknown> = {
      model: TTS_MODEL,
      messages: [
        {
          role: "assistant",
          content: text,
        },
      ],
      audio: {
        format: "wav",
        voice: voice || TTS_VOICE,
      },
      stream: false,
    };

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${TTS_API_KEY}`,
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

    const json = await response.json();
    const audioBase64 = json?.choices?.[0]?.message?.audio?.data;

    if (!audioBase64 || typeof audioBase64 !== "string") {
      return Response.json(
        { error: "TTS 响应格式异常，未获取到音频数据" },
        { status: 502 }
      );
    }

    const audioBuffer = Buffer.from(audioBase64, "base64");

    return new Response(audioBuffer, {
      headers: {
        "Content-Type": "audio/wav",
        "Content-Length": audioBuffer.length.toString(),
        "Cache-Control": "no-cache",
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
