import { NextRequest } from "next/server";
import { promises as fs } from "fs";
import path from "path";
import { scales } from "@/data/scales";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const TTS_URL = process.env.NEXT_PUBLIC_TTS_URL || "";
const TTS_API_KEY = process.env.NEXT_PUBLIC_TTS_API_KEY || "";
const TTS_MODEL = process.env.NEXT_PUBLIC_TTS_MODEL || "mimo-v2.5-tts";
const TTS_VOICE = process.env.NEXT_PUBLIC_TTS_VOICE || "冰糖";

const AUDIO_DIR = path.join(process.cwd(), "apps", "mvp", "public", "audio", "cga");

async function ensureDir() {
  try {
    await fs.access(AUDIO_DIR);
  } catch {
    await fs.mkdir(AUDIO_DIR, { recursive: true });
  }
}

async function synthesizeAudio(text: string): Promise<Buffer> {
  if (!TTS_URL || !TTS_API_KEY) {
    throw new Error("TTS_SERVICE_UNAVAILABLE");
  }

  const url = TTS_URL.replace(/\/+$/, "") + "/chat/completions";

  const requestBody = {
    model: TTS_MODEL,
    messages: [
      {
        role: "assistant",
        content: text,
      },
    ],
    audio: {
      format: "wav",
      voice: TTS_VOICE,
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
    throw new Error(`TTS 请求失败: HTTP ${response.status} ${errText}`);
  }

  const json = await response.json();
  const audioBase64 = json?.choices?.[0]?.message?.audio?.data;

  if (!audioBase64 || typeof audioBase64 !== "string") {
    throw new Error("TTS 响应格式异常");
  }

  return Buffer.from(audioBase64, "base64");
}

function generateSilentWav(durationMs: number = 100): Buffer {
  const sampleRate = 16000;
  const bitsPerSample = 16;
  const numChannels = 1;
  const numSamples = Math.floor(sampleRate * durationMs / 1000);
  const byteRate = sampleRate * numChannels * bitsPerSample / 8;
  const blockAlign = numChannels * bitsPerSample / 8;
  const dataSize = numSamples * blockAlign;
  const headerSize = 44;
  const fileSize = headerSize - 8 + dataSize;

  const buffer = Buffer.alloc(headerSize + dataSize);

  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(fileSize, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(numChannels, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(byteRate, 28);
  buffer.writeUInt16LE(blockAlign, 32);
  buffer.writeUInt16LE(bitsPerSample, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(dataSize, 40);

  for (let i = 0; i < dataSize; i++) {
    buffer[headerSize + i] = 0;
  }

  return buffer;
}

function buildTTSText(questionText: string, options: { label: string }[]): string {
  let text = questionText + "。";
  options.forEach((opt, i) => {
    text += `${i + 1}.${opt.label} `;
  });
  return text.trim();
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const scaleId = searchParams.get("scaleId");
    const qIndexStr = searchParams.get("qIndex");

    if (!scaleId || qIndexStr === null) {
      return Response.json(
        { error: "缺少 scaleId 或 qIndex 参数" },
        { status: 400 }
      );
    }

    const qIndex = parseInt(qIndexStr, 10);
    if (isNaN(qIndex) || qIndex < 0) {
      return Response.json(
        { error: "qIndex 参数无效" },
        { status: 400 }
      );
    }

    const scale = scales.find((s) => s.id === scaleId);
    if (!scale) {
      return Response.json(
        { error: "未找到对应的量表" },
        { status: 404 }
      );
    }

    const question = scale.questions[qIndex];
    if (!question) {
      return Response.json(
        { error: "未找到对应的题目" },
        { status: 404 }
      );
    }

    await ensureDir();

    const fileName = `${scaleId}_q${qIndex}.wav`;
    const filePath = path.join(AUDIO_DIR, fileName);

    try {
      const existingBuffer = await fs.readFile(filePath);
      return new Response(new Uint8Array(existingBuffer), {
        headers: {
          "Content-Type": "audio/wav",
          "Content-Length": existingBuffer.length.toString(),
          "Cache-Control": "public, max-age=31536000, immutable",
        },
      });
    } catch {
    }

    let audioBuffer: Buffer;
    try {
      const ttsText = buildTTSText(question.text, question.options || []);
      audioBuffer = await synthesizeAudio(ttsText);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (message === "TTS_SERVICE_UNAVAILABLE") {
        audioBuffer = generateSilentWav();
      } else {
        throw err;
      }
    }

    await fs.writeFile(filePath, audioBuffer);

    return new Response(new Uint8Array(audioBuffer), {
      headers: {
        "Content-Type": "audio/wav",
        "Content-Length": audioBuffer.length.toString(),
        "Cache-Control": "public, max-age=31536000, immutable",
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return Response.json(
      { error: `生成音频失败: ${message}` },
      { status: 500 }
    );
  }
}
