import { gerclawRequest } from "./client";
import {
  cgaAssessmentSchema,
  cgaActiveAssessmentsSchema,
  cgaComparisonSchema,
  cgaHistorySchema,
  cgaReportSchema,
  cgaScalesSchema,
  type CgaAssessment,
  type CgaComparison,
  type CgaReport,
  type CgaScaleId,
} from "./schemas";
import { z } from "zod";

const assessmentIdSchema = z.string().uuid();
const answerRequestSchema = z
  .object({
    expected_revision: z.number().int().positive(),
    question_id: z.string().regex(/^(?:phq9_[1-9]|sas_(?:[1-9]|1[0-9]|20)|psqi_(?:[1-9]|10|5[a-j])|minicog_(?:prepare|clock|recall)|mmse_(?:education|[1-9]|[12][0-9]|30))$/),
    score: z.number().int().min(0).max(1439),
    supplemental_detail: z.string().trim().min(1).max(500).optional(),
  })
  .strict();

export async function listCgaScales() {
  return gerclawRequest("cga/scales", cgaScalesSchema);
}

export async function startCgaAssessment(scaleId: CgaScaleId): Promise<CgaAssessment> {
  return gerclawRequest("cga/assessments", cgaAssessmentSchema, {
    method: "POST",
    body: JSON.stringify({ scale_id: scaleId }),
  });
}

export async function getCgaAssessment(assessmentId: string): Promise<CgaAssessment> {
  const parsedId = assessmentIdSchema.parse(assessmentId);
  return gerclawRequest(`cga/assessments/${encodeURIComponent(parsedId)}`, cgaAssessmentSchema);
}

export async function listCgaHistory() {
  return gerclawRequest("cga/assessments?limit=10", cgaHistorySchema);
}

export async function listActiveCgaAssessments() {
  return gerclawRequest("cga/assessments/active", cgaActiveAssessmentsSchema);
}

export async function submitCgaAnswer(
  assessment: CgaAssessment,
  questionId: string,
  score: number,
  supplementalDetail?: string
): Promise<CgaAssessment> {
  const parsedAssessment = cgaAssessmentSchema.parse(assessment);
  const payload = answerRequestSchema.parse({
    expected_revision: parsedAssessment.revision,
    question_id: questionId,
    score,
    ...(supplementalDetail?.trim() ? { supplemental_detail: supplementalDetail.trim() } : {}),
  });
  return gerclawRequest(
    `cga/assessments/${encodeURIComponent(parsedAssessment.assessment_id)}/answers`,
    cgaAssessmentSchema,
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  );
}

export async function completeCgaAssessment(assessment: CgaAssessment): Promise<CgaAssessment> {
  const parsedAssessment = cgaAssessmentSchema.parse(assessment);
  return gerclawRequest(
    `cga/assessments/${encodeURIComponent(parsedAssessment.assessment_id)}/complete`,
    cgaAssessmentSchema,
    { method: "POST", body: JSON.stringify({ expected_revision: parsedAssessment.revision }) }
  );
}

export async function getCgaReport(assessmentId: string): Promise<CgaReport> {
  const parsedId = assessmentIdSchema.parse(assessmentId);
  return gerclawRequest(
    `cga/assessments/${encodeURIComponent(parsedId)}/report`,
    cgaReportSchema
  );
}

export async function getCgaComparison(assessmentId: string): Promise<CgaComparison> {
  const parsedId = assessmentIdSchema.parse(assessmentId);
  return gerclawRequest(
    `cga/assessments/${encodeURIComponent(parsedId)}/comparison`,
    cgaComparisonSchema
  );
}
