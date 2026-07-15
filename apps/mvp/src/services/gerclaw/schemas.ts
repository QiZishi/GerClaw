import { z } from "zod";

const skillIdSchema = z.string().regex(/^[a-z][a-z0-9_.-]{1,63}$/);

export const skillInfoSchema = z
  .object({
    skill_id: skillIdSchema,
    name: z.string().min(1).max(100),
    description: z.string().min(1).max(500),
    version: z.string(),
    parameter_schema: z.record(z.string(), z.unknown()),
    tool_names: z.array(z.string()),
    category: z.string(),
    source: z.enum(["builtin", "custom"]),
    origin: z.enum(["builtin", "text", "upload", "generated"]),
    enabled: z.boolean(),
    revision: z.number().int().positive(),
    created_at: z.string().nullable(),
    updated_at: z.string().nullable(),
  })
  .strict();

export const skillDefinitionSchema = skillInfoSchema.extend({
  source_markdown: z.string().min(1).max(10_000),
});

export const skillListSchema = z.array(skillInfoSchema);
export const generatedSkillSchema = z
  .object({
    trace_id: z.string(),
    definition: skillDefinitionSchema,
  })
  .strict();
export const sessionSkillsSchema = z
  .object({
    session_id: z.string().uuid(),
    skill_ids: z.array(skillIdSchema),
  })
  .strict();
export const sessionSchema = z
  .object({
    id: z.string().uuid(),
    agent_id: z.string(),
    status: z.enum(["active", "archived", "deleted"]),
    created_at: z.string(),
    updated_at: z.string(),
  })
  .passthrough();

export type SkillInfo = z.infer<typeof skillInfoSchema>;
export type SkillDefinition = z.infer<typeof skillDefinitionSchema>;

const approvalStatusSchema = z.enum([
  "pending",
  "approved",
  "rejected",
  "expired",
  "cancelled",
]);

export const approvalSchema = z
  .object({
    id: z.string().uuid(),
    requester_actor_id: z.string().min(1),
    patient_id: z.string().uuid().nullable(),
    session_id: z.string().uuid(),
    trace_id: z.string().min(1),
    invocation_id: z.string().min(1),
    tool_name: z.string().min(1),
    tool_version: z.string().min(1),
    required_roles: z.array(z.string().min(1)),
    policy_version: z.string().min(1),
    status: approvalStatusSchema,
    revision: z.number().int().positive(),
    decided_by_actor_id: z.string().nullable(),
    expires_at: z.string().datetime(),
    created_at: z.string().datetime(),
    updated_at: z.string().datetime(),
  })
  .strict();

export type RuntimeApproval = z.infer<typeof approvalSchema>;

const cgaOptionSchema = z.tuple([z.number().int().min(0).max(3), z.string().min(1).max(80)]);
export const cgaQuestionSchema = z
  .object({
    id: z.string().regex(/^phq9_[1-9]$/),
    position: z.number().int().min(1).max(9),
    text: z.string().min(1).max(500),
    sensitive_prefix: z.string().min(1).max(200).nullable(),
    options: z.array(cgaOptionSchema).length(4),
  })
  .strict();
const cgaRiskSchema = z
  .object({
    requires_immediate_safety_assessment: z.boolean(),
    high_severity_follow_up: z.boolean(),
    messages: z.array(z.string().min(1).max(500)).max(2),
  })
  .strict();
export const cgaAssessmentSchema = z
  .object({
    assessment_id: z.string().uuid(),
    scale_id: z.literal("phq9"),
    definition_version: z.string().min(1).max(32),
    status: z.enum(["active", "completed", "abandoned"]),
    revision: z.number().int().positive(),
    answered_count: z.number().int().min(0).max(9),
    next_question: cgaQuestionSchema.nullable(),
    risk: cgaRiskSchema,
  })
  .strict();
export const cgaScalesSchema = z
  .object({
    scales: z.array(
      z
        .object({
          id: z.literal("phq9"),
          version: z.string().min(1).max(32),
          name: z.literal("PHQ-9"),
          description: z.string().min(1).max(200),
          question_count: z.literal(9),
          questions: z.array(cgaQuestionSchema).length(9),
        })
        .strict()
    ).length(1),
  })
  .strict();
export const cgaReportSchema = z
  .object({
    total_score: z.number().int().min(0).max(27),
    severity: z.enum(["minimal", "mild", "moderate", "moderately_severe", "severe"]),
    self_harm_signal: z.boolean(),
    requires_immediate_safety_assessment: z.boolean(),
    high_severity_follow_up: z.boolean(),
    safety_messages: z.array(z.string().min(1).max(500)).max(2),
    disclaimer: z.string().min(1).max(200),
  })
  .strict();

export type CgaAssessment = z.infer<typeof cgaAssessmentSchema>;
export type CgaQuestion = z.infer<typeof cgaQuestionSchema>;
export type CgaReport = z.infer<typeof cgaReportSchema>;
