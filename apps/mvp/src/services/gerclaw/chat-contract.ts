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
 * Required final payload and the exact server-owned transport metadata. New
 * fields require a versioned backend/frontend contract change; silently
 * accepting them would hide a protocol drift at a medical UI boundary.
 */
export const chatDoneEventSchema = z
  .object({
    full_text: z.string(),
    references: z.array(referenceSchema),
    trace_id: z.string(),
    session_id: z.string().uuid(),
    safety: safetySchema,
    replayed: z.boolean(),
    timestamp: z.number().finite().nonnegative(),
  })
  .strict();
