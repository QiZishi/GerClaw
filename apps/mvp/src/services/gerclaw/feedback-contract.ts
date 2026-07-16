import { z } from "zod";

export const traceIdSchema = z.string().regex(/^trace_[A-Za-z0-9][A-Za-z0-9_.:-]{7,57}$/);
export const feedbackIdempotencyKeySchema = z
  .string()
  .regex(/^idem_[A-Za-z0-9][A-Za-z0-9_.:-]{7,90}$/);
export const feedbackCategorySchema = z.string().regex(/^[a-z][a-z0-9_.-]{1,63}$/);

export const feedbackSubmitSchema = z
  .object({
    idempotency_key: feedbackIdempotencyKeySchema,
    trace_id: traceIdSchema,
    rating: z.enum(["positive", "negative"]),
    categories: z.array(feedbackCategorySchema).max(20),
    comment: z.string().max(2_000).optional(),
    metadata: z.record(z.string(), z.unknown()),
  })
  .strict();

export type FeedbackRating = z.infer<typeof feedbackSubmitSchema>["rating"];

export interface FeedbackSubmission {
  traceId: string;
  idempotencyKey: string;
  rating: FeedbackRating;
  comment?: string;
}

export function buildFeedbackPayload(input: FeedbackSubmission) {
  return feedbackSubmitSchema.parse({
    idempotency_key: input.idempotencyKey,
    trace_id: input.traceId,
    rating: input.rating,
    categories: [],
    ...(input.comment?.trim() ? { comment: input.comment.trim() } : {}),
    metadata: {},
  });
}
