import assert from "node:assert/strict";
import test from "node:test";

import { splitTtsText } from "./tts-text.ts";

test("TTS splits long text at natural sentence boundaries when possible", () => {
  const first = "第一句内容用于测试自然分段。";
  const second = "第二句内容稍长但不应在句号前截断。";
  const third = "第三句保留在下一段。";
  const result = splitTtsText(first + second + third, 40);
  assert.deepEqual(result, [first + second, third]);
  assert.ok(result.every((chunk) => chunk.length <= 40));
});

test("TTS has a bounded fallback for one long sentence", () => {
  const result = splitTtsText("甲".repeat(85), 40);
  assert.deepEqual(result.map((chunk) => chunk.length), [40, 40, 5]);
});
