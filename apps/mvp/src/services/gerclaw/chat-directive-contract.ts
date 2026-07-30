import { z } from "zod";

const traceIdSchema = z
  .string()
  .regex(/^trace_[A-Za-z0-9][A-Za-z0-9_.:-]{7,57}$/);

export const interruptedSchema = z
  .object({
    trace_id: traceIdSchema,
    status: z.literal("interrupted"),
    message: z.string().min(1).max(200),
  })
  .strict();

export const runDirectiveSchema = z
  .object({
    schema_version: z.literal("1.0"),
    id: z.string().uuid(),
    conversation_id: z.string().uuid(),
    target_run_id: z.string().uuid(),
    successor_run_id: z.string().uuid().nullable(),
    sequence: z.number().int().positive(),
    mode: z.enum(["interrupt_and_steer", "queue_for_next_boundary"]),
    status: z.enum([
      "pending",
      "pending_next_run",
      "claimed",
      "applied",
      "cancelled",
    ]),
    instruction: z.string().min(1).max(4_000),
    revision: z.number().int().positive(),
    created_at: z.string().datetime(),
    claimed_at: z.string().datetime().nullable(),
    applied_at: z.string().datetime().nullable(),
    cancelled_at: z.string().datetime().nullable(),
  })
  .strict();
