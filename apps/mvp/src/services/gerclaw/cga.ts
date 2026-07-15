import { gerclawRequest } from "./client";
import {
  cgaAssessmentSchema,
  cgaReportSchema,
  cgaScalesSchema,
  type CgaAssessment,
  type CgaReport,
} from "./schemas";

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
  return gerclawRequest(`cga/assessments/${encodeURIComponent(assessmentId)}`, cgaAssessmentSchema);
}

export async function submitCgaAnswer(
  assessment: CgaAssessment,
  questionId: string,
  score: number
): Promise<CgaAssessment> {
  return gerclawRequest(
    `cga/assessments/${encodeURIComponent(assessment.assessment_id)}/answers`,
    cgaAssessmentSchema,
    {
      method: "POST",
      body: JSON.stringify({
        expected_revision: assessment.revision,
        question_id: questionId,
        score,
      }),
    }
  );
}

export async function completeCgaAssessment(assessment: CgaAssessment): Promise<CgaAssessment> {
  return gerclawRequest(
    `cga/assessments/${encodeURIComponent(assessment.assessment_id)}/complete`,
    cgaAssessmentSchema,
    { method: "POST", body: JSON.stringify({ expected_revision: assessment.revision }) }
  );
}

export async function getCgaReport(assessmentId: string): Promise<CgaReport> {
  return gerclawRequest(
    `cga/assessments/${encodeURIComponent(assessmentId)}/report`,
    cgaReportSchema
  );
}
