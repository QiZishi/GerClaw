import assert from "node:assert/strict";
import test from "node:test";

import { pcm16leToWav } from "./pcm-wav.ts";

test("wraps PCM16LE in a 24 kHz mono WAV container", async () => {
  const blob = pcm16leToWav(new Uint8Array([1, 0, 255, 127]).buffer);
  const bytes = new Uint8Array(await blob.arrayBuffer());
  assert.equal(blob.type, "audio/wav");
  assert.equal(bytes.length, 48);
  assert.deepEqual([...bytes.slice(0, 4)], [82, 73, 70, 70]);
  assert.equal(new DataView(bytes.buffer).getUint32(24, true), 24_000);
  assert.deepEqual([...bytes.slice(44)], [1, 0, 255, 127]);
});

test("rejects empty and odd-byte PCM data", () => {
  assert.throws(() => pcm16leToWav(new ArrayBuffer(0)));
  assert.throws(() => pcm16leToWav(new ArrayBuffer(1)));
});
