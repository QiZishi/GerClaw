import { z } from "zod";
import { createHash } from "node:crypto";

const MAX_ASR_BASE64_CHARACTERS = 10 * 1024 * 1024;
const MAX_TTS_TEXT_CHARACTERS = 4_000;
const MAX_REQUEST_OVERHEAD_BYTES = 2_048;
const VOICE_REQUEST_WINDOW_MS = 60_000;
const MAX_VOICE_REQUESTS_PER_WINDOW = 12;
const MAX_ALL_VOICE_REQUESTS_PER_WINDOW = 120;
const TTS_VOICES = ["冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean"] as const;

const asrRequestSchema = z
  .object({
    audio: z.string().min(1).max(MAX_ASR_BASE64_CHARACTERS + 128),
    format: z.enum(["wav", "mp3"]).optional(),
  })
  .strict();

const ttsRequestSchema = z
  .object({
    text: z.string().trim().min(1).max(MAX_TTS_TEXT_CHARACTERS),
    voice: z.enum(TTS_VOICES).optional(),
  })
  .strict();

const requestWindows = new Map<string, { count: number; resetAt: number }>();
let globalWindow = { count: 0, resetAt: 0 };

export class VoiceRequestError extends Error {
  readonly status: 400 | 413 | 429;

  constructor(status: 400 | 413 | 429) {
    super("VOICE_REQUEST_INVALID");
    this.status = status;
  }
}

async function readJsonWithinLimit(
  request: Request,
  maxBytes: number,
  signal: AbortSignal
): Promise<unknown> {
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    throw new VoiceRequestError(400);
  }
  const contentLength = request.headers.get("content-length");
  if (contentLength !== null && Number(contentLength) > maxBytes) {
    throw new VoiceRequestError(413);
  }

  const reader = request.body?.getReader();
  if (!reader) throw new VoiceRequestError(400);
  const chunks: Uint8Array[] = [];
  let size = 0;
  const cancelRead = () => void reader.cancel(signal.reason);
  signal.addEventListener("abort", cancelRead, { once: true });
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maxBytes) {
        await reader.cancel();
        throw new VoiceRequestError(413);
      }
      chunks.push(value);
    }
  } finally {
    signal.removeEventListener("abort", cancelRead);
    reader.releaseLock();
  }
  if (signal.aborted) {
    throw signal.reason ?? new DOMException("The voice request was aborted", "AbortError");
  }
  const merged = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  const body = new TextDecoder().decode(merged);
  try {
    return JSON.parse(body) as unknown;
  } catch {
    throw new VoiceRequestError(400);
  }
}

export async function parseAsrRequest(
  request: Request,
  signal: AbortSignal
): Promise<{ audio: string; format: "wav" | "mp3" }> {
  const parsed = asrRequestSchema.safeParse(
    await readJsonWithinLimit(request, MAX_ASR_BASE64_CHARACTERS + MAX_REQUEST_OVERHEAD_BYTES, signal)
  );
  if (!parsed.success) throw new VoiceRequestError(400);

  const dataUrl = /^data:audio\/(wav|mpeg);base64,([A-Za-z0-9+/]+={0,2})$/.exec(parsed.data.audio);
  const inferredFormat = dataUrl ? (dataUrl[1] === "mpeg" ? "mp3" : "wav") : undefined;
  if (inferredFormat && parsed.data.format && parsed.data.format !== inferredFormat) {
    throw new VoiceRequestError(400);
  }
  const format = inferredFormat ?? parsed.data.format;
  const audio = dataUrl ? dataUrl[2] : parsed.data.audio;
  if (
    !format ||
    audio.length > MAX_ASR_BASE64_CHARACTERS ||
    audio.length % 4 !== 0 ||
    !/^[A-Za-z0-9+/]+={0,2}$/.test(audio)
  ) {
    throw new VoiceRequestError(400);
  }
  return { audio, format };
}

export async function parseTtsRequest(
  request: Request,
  signal: AbortSignal
): Promise<{ text: string; voice?: string }> {
  const parsed = ttsRequestSchema.safeParse(
    await readJsonWithinLimit(request, MAX_TTS_TEXT_CHARACTERS * 4 + MAX_REQUEST_OVERHEAD_BYTES, signal)
  );
  if (!parsed.success) throw new VoiceRequestError(400);
  return parsed.data;
}

function rateLimitKey(request: Request): string {
  const guestToken = /(?:^|;\s*)gerclaw_guest_token=([^;]+)/.exec(request.headers.get("cookie") ?? "")?.[1];
  return guestToken
    ? `guest:${createHash("sha256").update(guestToken).digest("hex")}`
    : "anonymous";
}

/** A local safety valve; the global bucket deliberately does not trust client-supplied IP headers. */
export function takeVoiceRequestSlot(request: Request): void {
  const key = rateLimitKey(request);
  const now = Date.now();
  if (globalWindow.resetAt <= now) {
    globalWindow = { count: 0, resetAt: now + VOICE_REQUEST_WINDOW_MS };
  }
  if (globalWindow.count >= MAX_ALL_VOICE_REQUESTS_PER_WINDOW) {
    throw new VoiceRequestError(429);
  }
  globalWindow.count += 1;
  if (requestWindows.size >= 1_000 && !requestWindows.has(key)) {
    for (const [candidate, value] of requestWindows) {
      if (value.resetAt <= now) requestWindows.delete(candidate);
    }
  }
  if (requestWindows.size >= 1_000 && !requestWindows.has(key)) {
    throw new VoiceRequestError(429);
  }
  const current = requestWindows.get(key);
  if (!current || current.resetAt <= now) {
    requestWindows.set(key, { count: 1, resetAt: now + VOICE_REQUEST_WINDOW_MS });
    return;
  }
  if (current.count >= MAX_VOICE_REQUESTS_PER_WINDOW) throw new VoiceRequestError(429);
  current.count += 1;
}

export function voiceErrorResponse(error: unknown): Response {
  if (error instanceof VoiceRequestError) {
    const errorMessage =
      error.status === 413
        ? "语音请求过大，请缩短录音或文字后重试。"
        : error.status === 429
          ? "语音服务请求过于频繁，请稍后重试。"
          : "语音请求格式不正确，请重试。";
    return Response.json({ error: errorMessage }, { status: error.status });
  }
  if (error instanceof DOMException && error.name === "TimeoutError") {
    return Response.json({ error: "语音服务响应超时，请稍后重试。" }, { status: 504 });
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return Response.json({ error: "语音请求已取消。" }, { status: 499 });
  }
  return Response.json({ error: "语音服务暂时不可用，请稍后重试。" }, { status: 502 });
}
