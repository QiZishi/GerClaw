import assert from "node:assert/strict";
import test from "node:test";
import {
  VoiceRequestError,
  parseAsrRequest,
  parseTtsRequest,
  takeVoiceRequestSlot,
  voiceErrorResponse,
} from "./voice-request.ts";

function jsonRequest(body, headers = {}) {
  return new Request("http://gerclaw.test/api/voice", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

test("ASR only accepts a bounded, declared WAV or MP3 base64 payload", async () => {
  const parsed = await parseAsrRequest(jsonRequest({ audio: "AQIDBA==", format: "wav" }), new AbortController().signal);
  assert.deepEqual(parsed, { audio: "AQIDBA==", format: "wav" });

  await assert.rejects(
    parseAsrRequest(jsonRequest({ audio: "data:audio/webm;base64,AQIDBA==" }), new AbortController().signal),
    (error) => error instanceof VoiceRequestError && error.status === 400
  );
  await assert.rejects(
    parseAsrRequest(jsonRequest({ audio: "data:audio/wav;base64,AQIDBA==", format: "mp3" }), new AbortController().signal),
    (error) => error instanceof VoiceRequestError && error.status === 400
  );
});

test("TTS rejects empty, oversized, unknown and extra fields before the provider call", async () => {
  const parsed = await parseTtsRequest(jsonRequest({ text: "请慢一点朗读", voice: "冰糖" }), new AbortController().signal);
  assert.deepEqual(parsed, { text: "请慢一点朗读", voice: "冰糖" });

  for (const body of [
    { text: "" },
    { text: "a".repeat(4_001) },
    { text: "您好", voice: "unknown" },
    { text: "您好", unexpected: true },
  ]) {
    await assert.rejects(
      parseTtsRequest(jsonRequest(body), new AbortController().signal),
      (error) => error instanceof VoiceRequestError && error.status === 400
    );
  }
});

test("request deadline cancels a stalled upload before provider access", async () => {
  let cancelled = false;
  const stalledBody = new ReadableStream({
    cancel() {
      cancelled = true;
    },
  });
  const request = new Request("http://gerclaw.test/api/voice/asr", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: stalledBody,
    duplex: "half",
  });
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(new DOMException("deadline", "TimeoutError")), 5);
  await assert.rejects(
    parseAsrRequest(request, controller.signal),
    (error) => error instanceof DOMException && error.name === "TimeoutError"
  );
  clearTimeout(timeout);
  assert.equal(cancelled, true);
});

test("voice request errors are stable and do not return upstream diagnostics", async () => {
  const response = voiceErrorResponse(new Error("provider leaked input: private audio"));
  const payload = await response.json();
  assert.equal(response.status, 502);
  assert.deepEqual(payload, { error: "语音服务暂时不可用，请稍后重试。" });
});

test("voice safety valve does not trust a client-supplied forwarding header", () => {
  const request = jsonRequest({ text: "您好" }, { "x-forwarded-for": "203.0.113.99" });
  for (let index = 0; index < 12; index += 1) takeVoiceRequestSlot(request);
  assert.throws(
    () => takeVoiceRequestSlot(jsonRequest({ text: "您好" }, { "x-forwarded-for": "198.51.100.1" })),
    (error) => error instanceof VoiceRequestError && error.status === 429
  );
});
