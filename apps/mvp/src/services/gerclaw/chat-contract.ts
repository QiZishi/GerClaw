import { z } from "zod";

const referenceSchema = z
  .object({
    source_id: z.string(),
    title: z.string(),
    locator: z.string(),
    excerpt: z.string(),
    score: z.number().nullable(),
    corpus: z.enum(["local_knowledge_base", "web", "uploaded_document", "uploaded_image"]),
  })
  .strict();

const safetySchema = z
  .object({
    reviewed: z.literal(true),
    disclaimer_applied: z.literal(true),
    deterministic_diagnosis_blocked: z.boolean(),
    high_risk_escalation_checked: z.literal(true),
    notices: z.array(z.string()).min(1).max(10),
  })
  .strict();

/**
 * Required final payload plus forward-compatible server transport metadata.
 * The API emits ``timestamp`` on every SSE event, so strict rejection of that
 * metadata must never convert a completed response into a client-side error.
 */
export const chatDoneEventSchema = z
  .object({
    full_text: z.string(),
    references: z.array(referenceSchema),
    trace_id: z.string(),
    session_id: z.string().uuid(),
    safety: safetySchema,
    replayed: z.boolean(),
  })
  .passthrough();
