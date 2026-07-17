import { z } from "zod";
import {
  feedbackCategorySchema,
  feedbackIdempotencyKeySchema,
  traceIdSchema,
} from "./feedback-contract";

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
export const skillDraftQualitySchema = z
  .object({
    version: z.literal("skill-draft-quality-v1"),
    review_required: z.literal(true),
    missing_checks: z.array(
      z.enum(["input_check", "local_evidence", "red_flag", "medical_disclaimer"])
    ).max(4),
  })
  .strict();
export const generatedSkillSchema = z
  .object({
    trace_id: z.string(),
    definition: skillDefinitionSchema,
    quality_report: skillDraftQualitySchema,
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
export type SkillDraft = z.infer<typeof generatedSkillSchema>;

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

export const cgaScaleIdSchema = z.enum(["phq9", "sas", "psqi"]);
const cgaOptionSchema = z.tuple([z.number().int().min(0).max(1439), z.string().min(1).max(80)]);
export const cgaQuestionSchema = z
  .object({
    id: z.string().regex(/^(?:phq9_[1-9]|sas_(?:[1-9]|1[0-9]|20)|psqi_(?:[1-9]|10|5[a-j]))$/),
    position: z.number().int().min(1).max(30),
    text: z.string().min(1).max(500),
    sensitive_prefix: z.string().min(1).max(200).nullable(),
    input_kind: z.enum(["ordinal", "clock_minutes", "duration_minutes"]),
    options: z.array(cgaOptionSchema).max(4),
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
    scale_id: cgaScaleIdSchema,
    definition_version: z.string().min(1).max(32),
    status: z.enum(["active", "completed", "abandoned"]),
    revision: z.number().int().positive(),
    answered_count: z.number().int().min(0).max(30),
    next_question: cgaQuestionSchema.nullable(),
    risk: cgaRiskSchema,
  })
  .strict();
export const cgaScalesSchema = z
  .object({
    scales: z.array(
      z
        .object({
          id: cgaScaleIdSchema,
          version: z.string().min(1).max(32),
          name: z.enum(["PHQ-9", "SAS", "PSQI"]),
          description: z.string().min(1).max(200),
          question_count: z.number().int().min(1).max(30),
          questions: z.array(cgaQuestionSchema).min(1).max(30),
        })
        .strict()
    ).min(1).max(3),
  })
  .strict();
export const cgaReportSchema = z
  .object({
    total_score: z.number().int().min(0).max(100),
    score_max: z.number().int().min(1).max(100),
    raw_score: z.number().int().min(0).max(100).nullable(),
    standard_score: z.number().int().min(0).max(100).nullable(),
    severity: z.enum(["none", "minimal", "mild", "moderate", "moderately_severe", "severe", "good", "fair", "average", "poor"]),
    self_harm_signal: z.boolean(),
    requires_immediate_safety_assessment: z.boolean(),
    high_severity_follow_up: z.boolean(),
    safety_messages: z.array(z.string().min(1).max(500)).max(2),
    component_scores: z.record(z.string().min(1).max(64), z.number().int().min(0).max(3)),
    disclaimer: z.string().min(1).max(200),
  })
  .strict();
export const cgaHistorySchema = z
  .object({
    items: z.array(
      z.object({
        assessment_id: z.string().uuid(),
        scale_id: cgaScaleIdSchema,
        definition_version: z.string().min(1).max(32),
        completed_at: z.string().datetime(),
        report: cgaReportSchema,
      }).strict()
    ).max(20),
  })
  .strict();
export const cgaComparisonSchema = z
  .object({
    status: z.enum(["comparable", "no_prior_same_scale", "definition_version_changed"]),
    current: z.object({
      assessment_id: z.string().uuid(),
      scale_id: cgaScaleIdSchema,
      definition_version: z.string().min(1).max(32),
      completed_at: z.string().datetime(),
      report: cgaReportSchema,
    }).strict(),
    prior: z.object({
      assessment_id: z.string().uuid(),
      scale_id: cgaScaleIdSchema,
      definition_version: z.string().min(1).max(32),
      completed_at: z.string().datetime(),
      report: cgaReportSchema,
    }).strict().nullable(),
    score_delta: z.number().int().min(-100).max(100).nullable(),
    disclaimer: z.string().min(1).max(200),
  })
  .strict();
export const cgaActiveAssessmentsSchema = z
  .object({
    items: z.array(cgaAssessmentSchema).max(3),
  })
  .strict();

export type CgaAssessment = z.infer<typeof cgaAssessmentSchema>;
export type CgaQuestion = z.infer<typeof cgaQuestionSchema>;
export type CgaReport = z.infer<typeof cgaReportSchema>;
export type CgaHistoryItem = z.infer<typeof cgaHistorySchema>["items"][number];
export type CgaComparison = z.infer<typeof cgaComparisonSchema>;
export type CgaActiveAssessment = z.infer<typeof cgaActiveAssessmentsSchema>["items"][number];
export type CgaScale = z.infer<typeof cgaScalesSchema>["scales"][number];
export type CgaScaleId = z.infer<typeof cgaScaleIdSchema>;

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

export const memoryFactSchema = z
  .object({
    id: z.string().uuid(),
    category: memoryCategorySchema,
    memory_type: z.enum(["stable", "evolving", "event"]),
    status: z.enum(["confirmed", "pending", "inactive"]),
    statement: z.string().min(1).max(1_000),
    details: z.record(z.string(), z.unknown()),
    confidence: z.number().min(0).max(1),
    revision: z.number().int().positive(),
    source_trace_id: z.string().min(1).max(64).nullable(),
    occurred_at: z.string().datetime().nullable(),
    confirmed_at: z.string().datetime().nullable(),
    updated_at: z.string().datetime(),
    relevance_score: z.number().min(0).max(1).nullable(),
  })
  .strict();

export const healthProfileSchema = z
  .object({
    schema_version: z.number().int().min(1),
    version: z.number().int().min(0),
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

export const memoryFactRevisionSchema = z
  .object({
    revision: z.number().int().positive(),
    category: memoryCategorySchema,
    memory_type: z.enum(["stable", "evolving", "event"]),
    status: z.enum(["confirmed", "pending", "inactive"]),
    statement: z.string().min(1).max(1_000),
    details: z.record(z.string(), z.unknown()),
    confidence: z.number().min(0).max(1),
    source_trace_id: z.string().min(1).max(64).nullable(),
    occurred_at: z.string().datetime().nullable(),
    confirmed_at: z.string().datetime().nullable(),
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

const chronicDateTimeSchema = z.string().datetime();

export const chronicConditionSchema = z
  .object({
    condition_id: z.string().uuid(),
    label: z.string().min(1).max(80),
    confirmation_status: z.literal("self_reported"),
    revision: z.number().int().positive(),
    created_at: chronicDateTimeSchema,
    updated_at: chronicDateTimeSchema,
  })
  .strict();

export const chronicConditionListSchema = z
  .object({ items: z.array(chronicConditionSchema).max(100) })
  .strict();

export const chronicMeasurementSchema = z
  .object({
    measurement_id: z.string().uuid(),
    condition_id: z.string().uuid(),
    metric_label: z.string().min(1).max(80),
    value: z.number().finite().min(0).max(10_000_000),
    unit: z.string().min(1).max(32),
    measured_at: chronicDateTimeSchema,
    created_at: chronicDateTimeSchema,
  })
  .strict();

export const chronicMeasurementListSchema = z
  .object({ items: z.array(chronicMeasurementSchema).max(200) })
  .strict();

export const chronicTrendSchema = z
  .object({
    metric_label: z.string().min(1).max(80),
    unit: z.string().min(1).max(32),
    direction: z.enum(["rising", "falling", "unchanged", "insufficient_data"]),
    latest_measurement_id: z.string().uuid(),
    latest_value: z.number().finite().min(0).max(10_000_000),
    latest_measured_at: chronicDateTimeSchema,
    previous_measurement_id: z.string().uuid().nullable(),
    previous_value: z.number().finite().min(0).max(10_000_000).nullable(),
    previous_measured_at: chronicDateTimeSchema.nullable(),
  })
  .strict();

export const chronicTrendListSchema = z
  .object({ items: z.array(chronicTrendSchema).max(100) })
  .strict();

export type ChronicCondition = z.infer<typeof chronicConditionSchema>;
export type ChronicMeasurement = z.infer<typeof chronicMeasurementSchema>;
export type ChronicTrend = z.infer<typeof chronicTrendSchema>;

export const riskAlertSchema = z
  .object({
    alert_id: z.string().uuid(),
    kind: z.enum([
      "cga_immediate_safety",
      "cga_high_follow_up",
      "chat_red_flag",
      "medication_contraindicated",
      "medication_major_risk",
    ]),
    severity: z.enum(["critical", "high"]),
    title: z.string().min(1).max(120),
    message: z.string().min(1).max(500),
    action: z.string().min(1).max(300),
    status: z.enum(["active", "acknowledged"]),
    revision: z.number().int().positive(),
    policy_version: z.enum(["risk-alert-v1", "risk-alert-v2"]),
    created_at: z.string().datetime(),
    updated_at: z.string().datetime(),
    acknowledged_at: z.string().datetime().nullable(),
  })
  .strict();

export const riskAlertListSchema = z.object({ items: z.array(riskAlertSchema).max(50) }).strict();
export type RiskAlert = z.infer<typeof riskAlertSchema>;

export const uploadedDocumentSchema = z
  .object({
    document_id: z.string().uuid(),
    session_id: z.string().uuid(),
    filename: z.string().min(1).max(255),
    media_type: z.enum([
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "text/markdown",
      "text/plain",
    ]),
    parse_source: z.enum(["mineru", "local_text"]),
    status: z.enum(["active", "revoked"]),
    content_characters: z.number().int().positive().max(1_000_000),
    created_at: z.string().datetime(),
  })
  .strict();
export const uploadedDocumentDeletedSchema = z
  .object({ document_id: z.string().uuid(), deleted: z.literal(true) })
  .strict();

export type UploadedDocument = z.infer<typeof uploadedDocumentSchema>;

const clinicalIntakeFieldSchema = z
  .object({
    id: z.string().regex(/^[a-z][a-z0-9_]{1,63}$/),
    label: z.string().min(1).max(200),
    required: z.boolean(),
    max_length: z.number().int().min(1).max(2_000),
    placeholder: z.string().min(1).max(300),
  })
  .strict();

export const clinicalIntakeSchema = z
  .object({
    intake_id: z.string().uuid(),
    session_id: z.string().uuid(),
    kind: z.enum(["prescription", "medication_review"]),
    definition_version: z.string().min(1).max(32),
    status: z.enum(["collecting", "information_complete_pending_governance"]),
    revision: z.number().int().positive(),
    conversation_turns: z.number().int().min(0).max(5),
    title: z.string().min(1).max(100),
    description: z.string().min(1).max(300),
    fields: z.array(clinicalIntakeFieldSchema).min(1).max(5),
    answers: z
      .record(z.string().regex(/^[a-z][a-z0-9_]{1,63}$/), z.string())
      .refine((answers) => Object.keys(answers).length <= 3, "最多保存 3 个信息字段"),
    document_ids: z.array(z.string().uuid()).max(10),
    image_evidence_ids: z.array(z.string().regex(/^ev_img[a-f0-9]{24}$/)).max(10),
    missing_required_fields: z.array(z.string().regex(/^[a-z][a-z0-9_]{1,63}$/)).max(3),
    governance_notice: z.string().min(1).max(500),
    updated_at: z.string().datetime(),
  })
  .strict();

export type ClinicalIntake = z.infer<typeof clinicalIntakeSchema>;

export const prescriptionConversationTurnSchema = z
  .object({
    intake: clinicalIntakeSchema,
    assistant_message: z.string().min(1).max(300),
    ready_to_generate: z.boolean(),
  })
  .strict();

export type PrescriptionConversationTurn = z.infer<typeof prescriptionConversationTurnSchema>;

const medicationListEntrySchema = z
  .object({
    position: z.number().int().min(1).max(50),
    text: z.string().min(1).max(1_500),
  })
  .strict();

const medicationDuplicateCandidateSchema = z
  .object({
    text: z.string().min(1).max(1_500),
    positions: z.array(z.number().int().min(1).max(50)).min(2).max(50),
  })
  .strict();

export const medicationReconciliationSchema = z
  .object({
    intake_id: z.string().uuid(),
    version: z.string().regex(/^medication-reconciliation-v[0-9]+$/),
    has_medication_list: z.boolean(),
    entries: z.array(medicationListEntrySchema).max(50),
    exact_duplicate_candidates: z.array(medicationDuplicateCandidateSchema).max(50),
    notice: z.string().min(1).max(500),
  })
  .strict();

export type MedicationReconciliation = z.infer<typeof medicationReconciliationSchema>;

const medicationRiskLevelSchema = z.enum(["contraindicated", "major", "moderate", "minor"]);
const medicationRuleSourceSchema = z
  .object({
    source_id: z.string().regex(/^[a-z][a-z0-9_]{2,63}$/),
    title: z.string().min(1).max(300),
    publisher: z.string().min(1).max(300),
    locator: z.string().min(1).max(500),
    local_corpus_path: z.string().min(1).max(500),
    content_sha256: z.string().regex(/^[a-f0-9]{64}$/),
    review_status: z.literal("source_traceable_pending_clinician_approval"),
  })
  .strict();

const reviewedMedicationSchema = z
  .object({
    position: z.number().int().min(1).max(50),
    text: z.string().min(1).max(1_500),
    recognized_generic_names: z.array(z.string().min(1)).max(4),
  })
  .strict();

const medicationReviewFindingSchema = z
  .object({
    finding_id: z.string().regex(/^[a-z][a-z0-9_]{2,95}$/),
    kind: z.enum(["ddi", "dose", "beers", "duplicate", "polypharmacy"]),
    severity: medicationRiskLevelSchema,
    title: z.string().min(1).max(300),
    involved_generic_names: z.array(z.string().min(1)).min(1).max(4),
    conclusion: z.string().min(1).max(1_000),
    clinician_action: z.string().min(1).max(1_000),
    elderly_note: z.string().min(1).max(1_000).nullable(),
    source_ids: z.array(z.string().min(1)).max(4),
    age_escalated: z.boolean(),
  })
  .strict();

export const medicationReviewDraftSchema = z
  .object({
    intake_id: z.string().uuid(),
    ruleset_version: z.string().regex(/^medication-rules-v[0-9]+$/),
    patient_age: z.number().int().min(0).max(130).nullable(),
    reviewed_medications: z.array(reviewedMedicationSchema).min(1).max(50),
    findings: z.array(medicationReviewFindingSchema).max(200),
    sources: z.array(medicationRuleSourceSchema).min(1).max(20),
    coverage: z
      .object({
        ddi: z.literal("limited_source_traceable"),
        dose: z.literal("limited_source_traceable"),
        beers: z.literal("limited_source_traceable"),
      })
      .strict(),
    unrecognized_entry_count: z.number().int().min(0).max(50),
    conclusion: z.string().min(1).max(1_000),
    disclaimer: z.literal(
      "本审查仅基于已安装且来源可追溯的有限规则，不能替代医师或药师的完整用药核对；不得据此自行开始、停用或调整剂量。"
    ),
  })
  .strict();

export type MedicationReviewDraft = z.infer<typeof medicationReviewDraftSchema>;

const prescriptionEvidenceSourceSchema = z
  .object({
    evidence_id: z.string().regex(/^ev_[a-z0-9]{8,64}$/),
    title: z.string().min(1).max(300),
    source: z.string().min(1).max(200),
    locator: z.string().min(1).max(500),
    url: z.string().url().max(2_000).nullable(),
  })
  .strict();

const prescriptionRecommendationSchema = z
  .object({
    content: z.string().min(1).max(2_000),
    evidence_ids: z.array(z.string().regex(/^ev_[a-z0-9]{8,64}$/)).min(1).max(8),
  })
  .strict();

const prescriptionSectionSchema = z
  .object({
    kind: z.enum(["medication", "exercise", "nutrition", "psychological", "rehabilitation"]),
    title: z.string().min(1).max(100),
    goal: z.string().min(1).max(1_000),
    recommendations: z.array(prescriptionRecommendationSchema).min(1).max(20),
    precautions: z.array(z.string().min(1).max(1_000)).min(1).max(20),
    evidence_ids: z.array(z.string().regex(/^ev_[a-z0-9]{8,64}$/)).min(1).max(20),
  })
  .strict();

const medicationDraftSchema = prescriptionSectionSchema
  .extend({
    kind: z.literal("medication"),
    medication_items: z.array(z.string().min(1).max(2_000)).max(30),
    monitoring_requirements: z.array(z.string().min(1).max(1_000)).max(20),
    review_required: z.literal(true),
  })
  .strict();

const exercisePhaseSchema = z
  .object({
    name: z.string().min(1).max(100),
    duration: z.string().min(1).max(200),
    intensity: z.string().min(1).max(500),
    instructions: z.string().min(1).max(2_000),
  })
  .strict();

const exerciseDraftSchema = prescriptionSectionSchema
  .extend({
    kind: z.literal("exercise"),
    contraindications: z.array(z.string().min(1).max(1_000)).min(1).max(20),
    phases: z.array(exercisePhaseSchema).min(1).max(6),
  })
  .strict();

const nutritionDraftSchema = prescriptionSectionSchema
  .extend({
    kind: z.literal("nutrition"),
    assessment_summary: z.string().min(1).max(2_000),
    target_energy_kcal: z.number().int().min(1).max(10_000).nullable(),
    target_protein_g: z.number().int().min(1).max(1_000).nullable(),
    monitoring: z.array(z.string().min(1).max(1_000)).min(1).max(20),
  })
  .strict();

const psychologicalDraftSchema = prescriptionSectionSchema
  .extend({
    kind: z.literal("psychological"),
    assessment_summary: z.string().min(1).max(2_000),
    follow_up: z.string().min(1).max(1_000),
    review_required: z.literal(true),
  })
  .strict();

const rehabilitationDraftSchema = prescriptionSectionSchema
  .extend({
    kind: z.literal("rehabilitation"),
    rehabilitation_type: z.string().min(1).max(200),
    functional_assessment: z.string().min(1).max(2_000),
    training_plan: z.array(z.string().min(1).max(1_000)).min(1).max(20),
    assistive_devices: z.array(z.string().min(1).max(1_000)).max(20),
    safety_precautions: z.array(z.string().min(1).max(1_000)).min(1).max(20),
  })
  .strict();

export const fivePrescriptionDraftSchema = z
  .object({
    template_version: z.literal("five-prescription-report-v1"),
    status: z.literal("needs_clinician_review"),
    patient_summary: z
      .object({
        age: z.number().int().min(0).max(130).nullable(),
        sex: z.enum(["female", "male", "other", "unknown"]),
        health_goals: z.array(z.string().min(1).max(1_000)).min(1).max(20),
        current_concerns: z.array(z.string().min(1).max(1_000)).min(1).max(20),
      })
      .strict(),
    health_assessment: z
      .object({
        summary: z.string().min(1).max(3_000),
        key_issues: z.array(z.string().min(1).max(1_000)).min(1).max(20),
        risk_factors: z.array(z.string().min(1).max(1_000)).max(20),
        clinician_review_required: z.literal(true),
      })
      .strict(),
    medication: medicationDraftSchema,
    exercise: exerciseDraftSchema,
    nutrition: nutritionDraftSchema,
    psychological: psychologicalDraftSchema,
    rehabilitation: rehabilitationDraftSchema,
    medication_review: medicationReviewDraftSchema.nullable(),
    evidence_sources: z.array(prescriptionEvidenceSourceSchema).min(1).max(100),
    uploaded_document_ids: z.array(z.string().uuid()).max(10),
    uploaded_image_evidence_ids: z.array(z.string().regex(/^ev_img[a-f0-9]{24}$/)).max(10),
    disclaimer: z.literal("AI生成建议仅供参考，不能替代专业医生诊断、治疗建议或处方；如有不适请及时就医。"),
  })
  .strict();

export type FivePrescriptionDraft = z.infer<typeof fivePrescriptionDraftSchema>;

export { feedbackSubmitSchema } from "./feedback-contract";

export const feedbackReadSchema = z
  .object({
    id: z.string().uuid(),
    idempotency_key: feedbackIdempotencyKeySchema,
    trace_id: traceIdSchema,
    actor_id: z.string().min(1).max(128),
    rating: z.enum(["positive", "negative"]),
    categories: z.array(feedbackCategorySchema).max(20),
    comment: z.string().nullable(),
    feedback_metadata: z.record(z.string(), z.unknown()),
    created_at: z.string().datetime(),
  })
  .strict();

export type FeedbackRead = z.infer<typeof feedbackReadSchema>;
