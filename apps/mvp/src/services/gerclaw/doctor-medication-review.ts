import { gerclawRequest } from "./client";
import {
  doctorMedicationReviewDraftListSchema,
  medicationReviewDraftReviewSchema,
  type DoctorMedicationReviewDraftList,
  type MedicationReviewDraftReview,
} from "./schemas";

function patientMedicationReviewPath(patientActorId: string): string {
  return `access-grants/patients/${encodeURIComponent(patientActorId.trim())}/medication-review-drafts`;
}

/** A doctor can read this narrow projection only after the patient's active grant. */
export function listAuthorizedMedicationReviewDrafts(
  patientActorId: string,
): Promise<DoctorMedicationReviewDraftList> {
  return gerclawRequest(
    patientMedicationReviewPath(patientActorId),
    doctorMedicationReviewDraftListSchema,
  );
}

export function submitMedicationReviewDraftReview(input: {
  patientActorId: string;
  draftId: string;
  decision: "approved" | "returned";
  reviewNote: string;
}): Promise<MedicationReviewDraftReview> {
  return gerclawRequest(
    `${patientMedicationReviewPath(input.patientActorId)}/${encodeURIComponent(input.draftId)}/reviews`,
    medicationReviewDraftReviewSchema,
    {
      method: "POST",
      body: JSON.stringify({ decision: input.decision, review_note: input.reviewNote.trim() }),
    }
  );
}
