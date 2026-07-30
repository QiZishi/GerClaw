import assert from "node:assert/strict";
import test from "node:test";

import {
  artifactDraftFromMessage,
  artifactTitleFromMarkdown,
} from "./artifact-draft.ts";
import type { Message } from "@/types";

const message: Message = {
  id: "message-1",
  sessionId: "session-1",
  role: "assistant",
  status: "done",
  createdAt: 1,
  executionRunId: "6cf3c10d-1d9e-4cfb-8d42-1e32fdb92911",
  blocks: [
    { kind: "text", id: "text-1", content: "# 跌倒预防建议\n\n- 保持通道照明。" },
    {
      kind: "action",
      id: "action-1",
      summary: "已生成引用列表",
      buttonLabel: "查看引用",
      panelType: "citations",
    },
  ],
};

test("artifact draft preserves Markdown and binds the producing run", () => {
  const draft = artifactDraftFromMessage(message, "request-1");
  assert.equal(draft.title, "跌倒预防建议");
  assert.equal(draft.markdown, "# 跌倒预防建议\n\n- 保持通道照明。");
  assert.equal(draft.runId, message.executionRunId);
  assert.equal(draft.sessionId, message.sessionId);
  assert.equal(draft.requestId, "request-1");
});

test("artifact title is bounded and has an honest empty fallback", () => {
  assert.equal(artifactTitleFromMarkdown(""), "AI 健康建议");
  assert.equal(artifactTitleFromMarkdown(`# ${"长".repeat(60)}`).length, 49);
});
