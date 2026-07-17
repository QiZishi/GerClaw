"use client";

import { gerclawRequest } from "./client";
import { ensureBackendSession } from "./skills";
import {
  clinicalIntakeSchema,
  fivePrescriptionDraftSchema,
  prescriptionDraftHistorySchema,
  medicationReconciliationSchema,
  medicationReviewDraftSchema,
  type ClinicalIntake,
  type FivePrescriptionDraft,
  type MedicationReconciliation,
  type MedicationReviewDraft,
  type PrescriptionConversationTurn,
  type PrescriptionDraftHistory,
  prescriptionConversationTurnSchema,
} from "./schemas";
import type { ImageAttachment } from "@/types";

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

export async function getMedicationReconciliation(
  intakeId: string
): Promise<MedicationReconciliation> {
  return gerclawRequest(
    `clinical-intakes/${encodeURIComponent(intakeId)}/medication-reconciliation`,
    medicationReconciliationSchema
  );
}

/** Generate a deterministic, source-traceable review; it is never a prescription. */
export async function generateMedicationReviewDraft(input: {
  intakeId: string;
  patientAge?: number;
}): Promise<MedicationReviewDraft> {
  return gerclawRequest(
    `clinical-intakes/${encodeURIComponent(input.intakeId)}/medication-review-draft`,
    medicationReviewDraftSchema,
    {
      method: "POST",
      body: JSON.stringify(
        input.patientAge === undefined ? {} : { patient_age: input.patientAge }
      ),
    }
  );
}

/** Generate a source-bound draft; it remains unavailable as a formal prescription. */
export async function generatePrescriptionDraft(intakeId: string): Promise<FivePrescriptionDraft> {
  return gerclawRequest(
    `clinical-intakes/${encodeURIComponent(intakeId)}/prescription-draft`,
    fivePrescriptionDraftSchema,
    { method: "POST" }
  );
}

/** Read the newest persisted drafts belonging to this intake's current owner. */
export async function listPrescriptionDrafts(intakeId: string): Promise<PrescriptionDraftHistory> {
  return gerclawRequest(
    `clinical-intakes/${encodeURIComponent(intakeId)}/prescription-drafts`,
    prescriptionDraftHistorySchema
  );
}

export async function processPrescriptionConversationTurn(input: {
  intakeId: string;
  expectedRevision: number;
  message: string;
  documentIds?: string[];
  images?: ImageAttachment[];
}): Promise<PrescriptionConversationTurn> {
  return gerclawRequest(
    `clinical-intakes/${encodeURIComponent(input.intakeId)}/conversation-turn`,
    prescriptionConversationTurnSchema,
    {
      method: "POST",
      body: JSON.stringify({
        expected_revision: input.expectedRevision,
        message: input.message,
        ...(input.documentIds === undefined ? {} : { document_ids: input.documentIds }),
        images: (input.images ?? []).map((image) => ({
          media_type: image.mimeType,
          base64: image.base64,
        })),
      }),
    }
  );
}

export async function updateClinicalIntake(input: {
  intakeId: string;
  expectedRevision: number;
  answers: Record<string, string>;
  documentIds?: string[];
  conversationTurnIncrement?: 1;
}): Promise<ClinicalIntake> {
  return gerclawRequest(`clinical-intakes/${encodeURIComponent(input.intakeId)}`, clinicalIntakeSchema, {
    method: "PATCH",
    body: JSON.stringify({
      expected_revision: input.expectedRevision,
      answers: input.answers,
      ...(input.documentIds === undefined ? {} : { document_ids: input.documentIds }),
      ...(input.conversationTurnIncrement === undefined
        ? {}
        : { conversation_turn_increment: input.conversationTurnIncrement }),
    }),
  });
}
