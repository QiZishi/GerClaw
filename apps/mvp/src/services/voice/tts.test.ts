import assert from "node:assert/strict";
import test from "node:test";

import { ApiError } from "../api-client.ts";
import { synthesizeSpeech } from "./tts.ts";

test("TTS unavailable response preserves a stable client code without backend details", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        detail: {
          code: "VOICE_TTS_UNAVAILABLE",
        },
      }),
      {
        status: 503,
        headers: { "content-type": "application/json" },
      },
    );
  try {
    await assert.rejects(
      synthesizeSpeech("请朗读这句话"),
      (error: unknown) =>
        error instanceof ApiError &&
        error.code === "VOICE_TTS_UNAVAILABLE" &&
        error.message === "语音朗读当前不可用" &&
        error.status === 503,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
