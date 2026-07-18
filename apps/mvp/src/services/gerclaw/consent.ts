import { gerclawRequest } from "./client";
import {
  patientAccessGrantListSchema,
  patientAccessGrantSchema,
  type PatientAccessGrant,
  type PatientAccessGrantList,
} from "./schemas";

/** Patient-controlled access is deliberately restricted to non-executable draft review. */
export function listPrescriptionReviewGrants(): Promise<PatientAccessGrantList> {
  return gerclawRequest("access-grants", patientAccessGrantListSchema);
}

export function grantPrescriptionReviewAccess(input: {
  doctorActorId: string;
  expiresAt: string;
}): Promise<PatientAccessGrantList> {
  return gerclawRequest("access-grants", patientAccessGrantListSchema, {
    method: "POST",
    body: JSON.stringify({
      doctor_actor_id: input.doctorActorId.trim(),
      resource_scopes: ["prescription_draft_review"],
      expires_at: input.expiresAt,
    }),
  });
}

export function revokePrescriptionReviewAccess(input: {
  grantId: string;
  expectedRevision: number;
}): Promise<PatientAccessGrant> {
  return gerclawRequest(
    `access-grants/${encodeURIComponent(input.grantId)}/revoke`,
    patientAccessGrantSchema,
    {
      method: "POST",
      body: JSON.stringify({ expected_revision: input.expectedRevision }),
    }
  );
}
