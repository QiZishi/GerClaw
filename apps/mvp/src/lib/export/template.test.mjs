import assert from "node:assert/strict";
import test from "node:test";

import {
  buildConversationMarkdown,
  buildConversationPlainText,
  MEDICAL_EXPORT_DISCLAIMER,
} from "./template.ts";

const messages = [
  { role: "user", content: "我最近头晕。" },
  { role: "assistant", content: "请记录症状并携带检查资料就医。" },
];

test("conversation Markdown and text exports retain visible messages and one medical disclaimer", () => {
  const markdown = buildConversationMarkdown("咨询记录", messages, "2026-07-18 10:00");
  const text = buildConversationPlainText("咨询记录", messages, "2026-07-18 10:00");

  for (const value of [markdown, text]) {
    assert.match(value, /我最近头晕。/);
    assert.match(value, /请记录症状并携带检查资料就医。/);
    assert.match(value, new RegExp(MEDICAL_EXPORT_DISCLAIMER));
  }
  assert.equal((markdown.match(/医疗免责声明/g) ?? []).length, 1);
  assert.equal((text.match(/医疗免责声明/g) ?? []).length, 1);
});
