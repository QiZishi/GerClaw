import type { Message } from "../types/chat.ts";

const MAX_MESSAGES_PER_SESSION = 50;

type LegacyMessageWithFeedbackText = Message & {
  feedbackText?: unknown;
};

function removePrivateFeedbackText(message: Message): Message {
  const safeMessage = { ...message } as LegacyMessageWithFeedbackText;
  delete safeMessage.feedbackText;
  return safeMessage;
}

export function truncateMessages(
  messagesBySession: Record<string, Message[]>,
): Record<string, Message[]> {
  const result: Record<string, Message[]> = {};
  for (const [sessionId, messages] of Object.entries(messagesBySession)) {
    if (!Array.isArray(messages)) continue;
    result[sessionId] = messages
      .slice(-MAX_MESSAGES_PER_SESSION)
      .map(removePrivateFeedbackText);
  }
  return result;
}
