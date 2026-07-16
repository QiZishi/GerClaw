"use client";

import { gerclawRequest } from "./client";
import { ensureBackendSession } from "./skills";
import { clinicalIntakeSchema, type ClinicalIntake } from "./schemas";

export type ClinicalIntakeKind = "prescription" | "medication_review";

export async function startClinicalIntake(input: {
  localSessionId: string;
  kind: ClinicalIntakeKind;
}): Promise<ClinicalIntake> {
  const sessionId = await ensureBackendSession(input.localSessionId);
  return gerclawRequest("clinical-intakes", clinicalIntakeSchema, {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, kind: input.kind }),
  });
}

export async function getClinicalIntake(intakeId: string): Promise<ClinicalIntake> {
  return gerclawRequest(`clinical-intakes/${encodeURIComponent(intakeId)}`, clinicalIntakeSchema);
}

export async function updateClinicalIntake(input: {
  intakeId: string;
  expectedRevision: number;
  answers: Record<string, string>;
}): Promise<ClinicalIntake> {
  return gerclawRequest(`clinical-intakes/${encodeURIComponent(input.intakeId)}`, clinicalIntakeSchema, {
    method: "PATCH",
    body: JSON.stringify({
      expected_revision: input.expectedRevision,
      answers: input.answers,
    }),
  });
}
