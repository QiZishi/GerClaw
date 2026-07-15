import { gerclawRequest } from "./client";
import {
  cgaAssessmentSchema,
  cgaReportSchema,
  cgaScalesSchema,
  type CgaAssessment,
  type CgaReport,
} from "./schemas";
import { z } from "zod";

const assessmentIdSchema = z.string().uuid();
const answerRequestSchema = z
  .object({
    expected_revision: z.number().int().positive(),
    question_id: z.string().regex(/^phq9_[1-9]$/),
    score: z.number().int().min(0).max(3),
  })
  .strict();

export async function listCgaScales() {
  return gerclawRequest("cga/scales", cgaScalesSchema);
}

export async function startPhq9Assessment(): Promise<CgaAssessment> {
  return gerclawRequest("cga/assessments", cgaAssessmentSchema, {
    method: "POST",
    body: JSON.stringify({ scale_id: "phq9" }),
  });
}

export async function getCgaAssessment(assessmentId: string): Promise<CgaAssessment> {
  const parsedId = assessmentIdSchema.parse(assessmentId);
  return gerclawRequest(`cga/assessments/${encodeURIComponent(parsedId)}`, cgaAssessmentSchema);
}

export async function submitCgaAnswer(
  assessment: CgaAssessment,
  questionId: string,
  score: number
): Promise<CgaAssessment> {
  const parsedAssessment = cgaAssessmentSchema.parse(assessment);
  const payload = answerRequestSchema.parse({
    expected_revision: parsedAssessment.revision,
    question_id: questionId,
    score,
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
