import { gerclawRequest } from "./client";
import {
  doctorMedicationReviewDraftListSchema,
  type DoctorMedicationReviewDraftList,
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
