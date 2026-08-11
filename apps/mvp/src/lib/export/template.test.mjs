import assert from "node:assert/strict";
import test from "node:test";

import {
  buildMarkdownDocument,
  buildConversationMarkdown,
  buildConversationPlainText,
  MEDICAL_EXPORT_DISCLAIMER,
} from "./template.ts";

const PRESCRIPTION_DISCLAIMER =
  "AI生成建议仅供参考，不能替代专业医生诊断、治疗建议或处方；如有不适请及时就医。";

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

test("prescription Markdown keeps its server-owned disclaimer without appending a duplicate", () => {
  const markdown = buildMarkdownDocument({
    title: "五大处方报告",
    content: `## 药物处方\n\n待临床复核。\n\n> ${PRESCRIPTION_DISCLAIMER}`,
    date: "2026-08-11 10:00",
    contentIncludesMedicalDisclaimer: true,
  });

  assert.match(markdown, /## 药物处方/);
  assert.equal((markdown.match(new RegExp(PRESCRIPTION_DISCLAIMER, "g")) ?? []).length, 1);
  assert.doesNotMatch(markdown, new RegExp(MEDICAL_EXPORT_DISCLAIMER));
});
