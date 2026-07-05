import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ASR_URL = process.env.NEXT_PUBLIC_ASR_URL || "";
const ASR_API_KEY = process.env.NEXT_PUBLIC_ASR_API_KEY || "";
const ASR_MODEL = process.env.NEXT_PUBLIC_ASR_MODEL || "mimo-v2.5-asr";

export async function POST(request: NextRequest) {
  if (!ASR_URL || !ASR_API_KEY) {
    return Response.json(
      { error: "ASR 服务未配置，请检查环境变量" },
      { status: 503 }
    );
  }

  try {
    const body = await request.json();
    let { audio, format } = body;

    if (!audio || typeof audio !== "string") {
      return Response.json(
        { error: "缺少音频数据" },
        { status: 400 }
      );
    }

    // 处理 data URL 格式（data:audio/xxx;base64,...），提取纯 base64
    if (audio.startsWith("data:")) {
      const commaIndex = audio.indexOf(",");
      if (commaIndex === -1) {
        return Response.json(
          { error: "音频数据格式无效" },
          { status: 400 }
        );
      }
      // 从 MIME type 推断格式
      const mimeHeader = audio.slice(5, commaIndex);
      if (!format) {
        if (mimeHeader.includes("wav")) format = "wav";
        else if (mimeHeader.includes("webm")) format = "webm";
        else if (mimeHeader.includes("mp4") || mimeHeader.includes("m4a")) format = "mp4";
        else if (mimeHeader.includes("ogg")) format = "ogg";
        else if (mimeHeader.includes("mpeg") || mimeHeader.includes("mp3")) format = "mp3";
      }
      audio = audio.slice(commaIndex + 1);
    }

    const url = ASR_URL.replace(/\/+$/, "") + "/chat/completions";

    const audioFormat = format || "wav";

    const requestBody: Record<string, unknown> = {
      model: ASR_MODEL,
      messages: [
        {
          role: "user",
          content: [
            {
              type: "input_audio",
              input_audio: {
                data: audio,
                format: audioFormat,
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
        Authorization: `Bearer ${ASR_API_KEY}`,
      },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const errText = await response.text();
      return Response.json(
        { error: `ASR 请求失败: HTTP ${response.status} ${errText}` },
        { status: response.status }
      );
    }

    const json = await response.json();
    const text = json?.choices?.[0]?.message?.content;

    if (typeof text !== "string") {
      return Response.json(
        { error: "ASR 响应格式异常，未获取到识别文本" },
        { status: 502 }
      );
    }

    return Response.json({ text: text.trim() });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return Response.json(
      { error: `ASR 服务异常: ${message}` },
      { status: 500 }
    );
  }
}
