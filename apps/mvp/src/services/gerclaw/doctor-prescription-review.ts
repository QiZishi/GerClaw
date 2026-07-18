import { gerclawRequest } from "./client";
import {
  doctorPrescriptionDraftListSchema,
  prescriptionDraftReviewSchema,
  type DoctorPrescriptionDraftList,
  type PrescriptionDraftReview,
} from "./schemas";

function patientDraftPath(patientActorId: string): string {
  return `access-grants/patients/${encodeURIComponent(patientActorId.trim())}/prescription-drafts`;
}

/** A doctor can only reach this projection after the patient's active, scoped grant. */
export function listAuthorizedPrescriptionDrafts(patientActorId: string): Promise<DoctorPrescriptionDraftList> {
  return gerclawRequest(patientDraftPath(patientActorId), doctorPrescriptionDraftListSchema);
}

export function submitPrescriptionDraftReview(input: {
  patientActorId: string;
  draftId: string;
  decision: "approved" | "returned";
  reviewNote: string;
  amendedMarkdown?: string;
  amendmentEvidenceIds?: string[];
}): Promise<PrescriptionDraftReview> {
  return gerclawRequest(
    `${patientDraftPath(input.patientActorId)}/${encodeURIComponent(input.draftId)}/reviews`,
    prescriptionDraftReviewSchema,
    {
      method: "POST",
      body: JSON.stringify({
        decision: input.decision,
        review_note: input.reviewNote.trim(),
        amended_markdown: input.amendedMarkdown?.trim() || null,
        amendment_evidence_ids: input.amendmentEvidenceIds ?? [],
      }),
    }
  );
}
