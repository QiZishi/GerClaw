import { gerclawRequest } from "./client";
import { feedbackReadSchema, type FeedbackRead } from "./schemas";
import { buildFeedbackPayload, type FeedbackSubmission } from "./feedback-contract";

export type { FeedbackRating, FeedbackSubmission } from "./feedback-contract";

export function createFeedbackIdempotencyKey(): string {
  return `idem_${crypto.randomUUID().replaceAll("-", "")}`;
}

export async function submitFeedback(input: FeedbackSubmission): Promise<FeedbackRead> {
  const payload = buildFeedbackPayload(input);
  return gerclawRequest("feedback", feedbackReadSchema, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
