import { z } from "zod";

const identifierSchema = z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$/);
const runStatusSchema = z.enum([
  "running",
  "waiting_for_user",
  "completed",
  "completed_with_warnings",
  "failed",
  "cancelled",
  "interrupted",
]);
const artifactKindSchema = z.enum(["markdown", "report", "prescription", "cga"]);
const boundedPayloadSchema = z
  .record(z.string(), z.json())
  .refine((value) => Object.keys(value).length <= 50, "payload has too many keys");

export const agentRunSchema = z
  .object({
    schema_version: z.literal("1.0"),
    id: z.string().uuid(),
    conversation_id: z.string().uuid(),
    input_message_id: z.string().uuid(),
    trace_id: identifierSchema,
    route: z.enum(["quick", "standard", "deep", "emergency"]),
    status: runStatusSchema,
    current_answer_version_id: z.string().uuid().nullable(),
    warnings: z.array(identifierSchema).max(50),
    last_sequence: z.number().int().nonnegative(),
    revision: z.number().int().positive(),
    started_at: z.string().datetime(),
    completed_at: z.string().datetime().nullable(),
  })
  .strict();

export const runEventSchema = z
  .object({
    schema_version: z.literal("1.0"),
    run_id: z.string().uuid(),
    sequence: z.number().int().positive(),
    event_type: identifierSchema,
    status: identifierSchema,
    public_summary: z.string().min(1).max(5_000).nullable(),
    payload: boundedPayloadSchema,
    duration_ms: z.number().int().nonnegative().nullable(),
    created_at: z.string().datetime(),
  })
  .strict();

export const runEventPageSchema = z
  .object({
    run_id: z.string().uuid(),
    events: z.array(runEventSchema).max(500),
    next_after_sequence: z.number().int().nonnegative(),
  })
  .strict();

export const answerVersionSchema = z
  .object({
    schema_version: z.literal("1.0"),
    id: z.string().uuid(),
    run_id: z.string().uuid(),
    answer_group_id: z.string().uuid(),
    assistant_message_id: z.string().uuid().nullable(),
    version: z.number().int().positive(),
    is_current: z.boolean(),
    supersedes_id: z.string().uuid().nullable(),
    created_at: z.string().datetime(),
  })
  .strict();

export const answerVersionListSchema = z
  .object({
    run_id: z.string().uuid(),
    versions: z.array(answerVersionSchema).max(100),
  })
  .strict();

export const answerVersionSelectSchema = z
  .object({ expected_current_version_id: z.string().uuid() })
  .strict();

export const artifactWriteSchema = z
  .object({
    title: z.string().trim().min(1).max(300),
    markdown: z.string().max(500_000),
    kind: artifactKindSchema.default("markdown"),
    expected_revision: z.number().int().positive().nullable().optional(),
  })
  .strict();

export const artifactSchema = z
  .object({
    schema_version: z.literal("1.0"),
    id: z.string().uuid(),
    run_id: z.string().uuid(),
    conversation_id: z.string().uuid(),
    title: z.string().trim().min(1).max(300),
    markdown: z.string().max(500_000),
    kind: artifactKindSchema,
    revision: z.number().int().positive(),
    saved: z.boolean(),
    created_at: z.string().datetime(),
    updated_at: z.string().datetime(),
  })
  .strict();

export const artifactListSchema = z
  .object({
    conversation_id: z.string().uuid(),
    artifacts: z.array(artifactSchema).max(100),
  })
  .strict();

export const artifactDeletedSchema = z
  .object({
    artifact_id: z.string().uuid(),
    deleted: z.literal(true),
  })
  .strict();

export const feedbackReconcileSchema = z
  .object({
    value: z.union([z.literal(-1), z.literal(0), z.literal(1)]),
    expected_revision: z.number().int().nonnegative(),
  })
  .strict();

export const feedbackStateSchema = z
  .object({
    schema_version: z.literal("1.0"),
    run_id: z.string().uuid(),
    value: z.union([z.literal(-1), z.literal(0), z.literal(1)]),
    revision: z.number().int().positive(),
    updated_at: z.string().datetime(),
  })
  .strict();

export type AgentRun = z.infer<typeof agentRunSchema>;
export type RunEventPage = z.infer<typeof runEventPageSchema>;
export type AnswerVersion = z.infer<typeof answerVersionSchema>;
export type Artifact = z.infer<typeof artifactSchema>;
export type ArtifactWrite = z.input<typeof artifactWriteSchema>;
export type FeedbackState = z.infer<typeof feedbackStateSchema>;
