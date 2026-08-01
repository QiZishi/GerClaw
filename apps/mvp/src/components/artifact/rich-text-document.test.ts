import assert from "node:assert/strict";
import test from "node:test";

import {
  artifactMarkdownToRichHtml,
  richHtmlToPlainText,
  sanitizeRichHtml,
} from "./rich-text-document.ts";

test("legacy Markdown becomes rendered editable document HTML", () => {
  const html = artifactMarkdownToRichHtml(
    "# 随访计划\n\n- **记录血压**\n- 查看[指南](https://example.test/guide)",
  );

  assert.match(html, /<h1>随访计划<\/h1>/);
  assert.match(html, /<ul><li><strong>记录血压<\/strong><\/li>/);
  assert.match(html, /href="https:\/\/example\.test\/guide"/);
  assert.equal(html.includes("# 随访计划"), false);
  assert.equal(html.includes("**记录血压**"), false);
});

test("stored rich document keeps formatting while unsafe browser markup is removed", () => {
  const stored = artifactMarkdownToRichHtml(
    '<!-- gerclaw-rich-document -->\n<p onclick="steal()"><u>重点</u></p><script>alert(1)</script>',
  );
  const sanitized = sanitizeRichHtml(stored);

  assert.match(sanitized, /<u>重点<\/u>/);
  assert.equal(sanitized.includes("onclick"), false);
  assert.equal(sanitized.includes("script"), false);
});

test("copy and text export consume rendered text instead of Markdown or HTML markers", () => {
  const plain = richHtmlToPlainText("<h2>用药记录</h2><p><strong>早晨</strong>一次</p>");

  assert.equal(plain, "用药记录\n早晨一次");
});
