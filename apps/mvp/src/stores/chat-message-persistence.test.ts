import assert from "node:assert/strict";
import test from "node:test";

import { truncateMessages } from "./chat-message-persistence.ts";
import type { Message } from "../types/chat.ts";

function message(id: string): Message {
  return {
    id,
    sessionId: "session_feedback_privacy",
    role: "assistant",
    blocks: [{ kind: "text", id: `block_${id}`, content: "测试回答" }],
    status: "done",
    createdAt: 1,
  };
}

test("local message persistence removes legacy feedback comments", () => {
  const legacyMessage = {
    ...message("message_feedback_privacy"),
    feedback: "down" as const,
    feedbackText: "包含健康信息的旧评论",
  };

  const sanitized = truncateMessages({
    session_feedback_privacy: [legacyMessage],
  });

  assert.equal(
    "feedbackText" in sanitized.session_feedback_privacy[0],
    false,
  );
  assert.equal(sanitized.session_feedback_privacy[0].feedback, "down");
});

test("local message persistence keeps only the newest bounded messages", () => {
  const messages = Array.from({ length: 51 }, (_, index) =>
    message(`message_${index}`),
  );

  const sanitized = truncateMessages({ session_feedback_privacy: messages });

  assert.equal(sanitized.session_feedback_privacy.length, 50);
  assert.equal(sanitized.session_feedback_privacy[0].id, "message_1");
});
