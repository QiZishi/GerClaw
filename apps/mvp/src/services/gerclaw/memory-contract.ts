import { z } from "zod";

const memoryCategorySchema = z.enum([
  "basic_info",
  "allergy",
  "condition",
  "medication",
  "vital_sign",
  "assessment",
  "event",
  "social",
  "preference",
  "goal",
]);
const optionalMemoryText = (maxLength: number) =>
  z.string().trim().min(1).max(maxLength).nullable().optional();
const memoryDetailsSchema = z
  .object({
    value: optionalMemoryText(200),
    unit: optionalMemoryText(32),
    dose: optionalMemoryText(100),
    frequency: optionalMemoryText(100),
    route: optionalMemoryText(64),
    reaction: optionalMemoryText(200),
    severity: z.enum(["mild", "moderate", "severe", "unknown"]).nullable().optional(),
    code: optionalMemoryText(32),
    level: optionalMemoryText(100),
    source_status: z
      .enum(["active", "stopped", "resolved", "historical", "unknown"])
      .optional(),
  })
  .strict();
const memoryAccessLevelSchema = z.enum(["standard", "restricted"]);

export const memoryFactCreateInputSchema = z
  .object({
    expected_profile_version: z.number().int().nonnegative(),
    category: memoryCategorySchema,
    memory_type: z.enum(["stable", "evolving", "event"]),
    entity: z.string().trim().min(1).max(120),
    statement: z.string().trim().min(1).max(1_000),
    details: memoryDetailsSchema.optional(),
    access_level: memoryAccessLevelSchema.optional(),
    occurred_at: z.string().datetime().nullable().optional(),
  })
  .strict()
  .superRefine((value, context) => {
    if (value.category === "basic_info" && value.details?.value == null) {
      context.addIssue({
        code: "custom",
        path: ["details", "value"],
        message: "basic information requires a value",
      });
    }
    if (
      value.category === "medication" &&
      ["药", "药物", "medication"].includes(value.entity.toLocaleLowerCase())
    ) {
      context.addIssue({
        code: "custom",
        path: ["entity"],
        message: "medication entity must name the medicine",
      });
    }
    if (
      value.category === "vital_sign" &&
      (value.details?.value == null || value.details?.unit == null)
    ) {
      context.addIssue({
        code: "custom",
        path: ["details"],
        message: "vital sign requires value and unit",
      });
    }
  });

export const memoryFactUpdateInputSchema = z
  .object({
    expected_revision: z.number().int().positive(),
    statement: z.string().trim().min(1).max(1_000).optional(),
    details: memoryDetailsSchema.optional(),
    access_level: memoryAccessLevelSchema.optional(),
    occurred_at: z.string().datetime().nullable().optional(),
  })
  .strict()
  .refine(
    (value) =>
      value.statement !== undefined ||
      value.details !== undefined ||
      value.access_level !== undefined ||
      value.occurred_at !== undefined,
    "memory update requires a mutable field"
  )
  .refine(
    (value) =>
      (value.details === undefined && value.occurred_at === undefined) ||
      value.statement !== undefined,
    "semantic memory changes require a new supporting statement"
  );

export const memoryFactDeleteInputSchema = z
  .object({
    expected_revision: z.number().int().positive(),
    reason: z.enum(["user_deleted", "outdated", "incorrect", "duplicate"]),
  })
  .strict();

export const memoryFactRestoreInputSchema = z
  .object({ expected_revision: z.number().int().positive() })
  .strict();

export const memoryFactSchema = z
  .object({
    id: z.string().uuid(),
    category: memoryCategorySchema,
    memory_type: z.enum(["stable", "evolving", "event"]),
    status: z.enum(["proposed", "confirmed", "conflicted", "pending", "inactive"]),
    access_level: memoryAccessLevelSchema,
    statement: z.string().min(1).max(1_000),
    details: z.record(z.string(), z.unknown()),
    confidence: z.number().min(0).max(1),
    revision: z.number().int().positive(),
    source_trace_id: z.string().min(1).max(64).nullable(),
    occurred_at: z.string().datetime().nullable(),
    confirmed_at: z.string().datetime().nullable(),
    expires_at: z.string().datetime().nullable(),
    tombstoned_at: z.string().datetime().nullable(),
    tombstone_reason: z
      .enum(["user_deleted", "outdated", "incorrect", "duplicate"])
      .nullable(),
    can_restore: z.boolean(),
    updated_at: z.string().datetime(),
    relevance_score: z.number().min(0).max(1).nullable(),
  })
  .strict();

export const healthProfileSchema = z
  .object({
    schema_version: z.number().int().min(1),
    version: z.number().int().min(0),
    cross_session_recall_enabled: z.boolean(),
    profile: z.record(z.string(), z.unknown()),
    facts: z.array(memoryFactSchema).max(200),
  })
  .strict();

export const memoryFactDecisionSchema = z
  .object({
    fact: memoryFactSchema,
    profile_version: z.number().int().positive(),
  })
  .strict();

export const memoryFactMutationSchema = memoryFactDecisionSchema;

export const memoryRecallPreferenceSchema = z
  .object({
    enabled: z.boolean(),
    profile_version: z.number().int().positive(),
  })
  .strict();

export const memoryFactRevisionSchema = z
  .object({
    revision: z.number().int().positive(),
    activity: z.enum([
      "legacy_update",
      "extraction_update",
      "user_decision",
      "user_update",
      "user_delete",
      "user_restore",
    ]),
    category: memoryCategorySchema,
    memory_type: z.enum(["stable", "evolving", "event"]),
    status: z.enum(["proposed", "confirmed", "conflicted", "pending", "inactive"]),
    access_level: memoryAccessLevelSchema,
    statement: z.string().min(1).max(1_000),
    details: z.record(z.string(), z.unknown()),
    confidence: z.number().min(0).max(1),
    source_trace_id: z.string().min(1).max(64).nullable(),
    occurred_at: z.string().datetime().nullable(),
    confirmed_at: z.string().datetime().nullable(),
    expires_at: z.string().datetime().nullable(),
    tombstoned_at: z.string().datetime().nullable(),
    tombstone_reason: z
      .enum(["user_deleted", "outdated", "incorrect", "duplicate"])
      .nullable(),
    updated_at: z.string().datetime().nullable(),
    recorded_at: z.string().datetime(),
  })
  .strict();

export const memoryFactHistorySchema = z
  .object({
    fact_id: z.string().uuid(),
    items: z.array(memoryFactRevisionSchema).max(50),
  })
  .strict();

export type HealthProfile = z.infer<typeof healthProfileSchema>;
export type MemoryFact = z.infer<typeof memoryFactSchema>;
export type MemoryFactHistory = z.infer<typeof memoryFactHistorySchema>;
export type CreateMemoryFactInput = z.infer<typeof memoryFactCreateInputSchema>;
export type UpdateMemoryFactInput = z.infer<typeof memoryFactUpdateInputSchema>;
