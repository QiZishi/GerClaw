import { gerclawRequest } from "./client";
import {
  patientAccessGrantListSchema,
  patientAccessGrantSchema,
  type PatientAccessGrant,
  type PatientAccessGrantList,
} from "./schemas";

export type PatientGrantResource = PatientAccessGrant["resource_scope"];

export function listPrescriptionReviewGrants(): Promise<PatientAccessGrantList> {
  return gerclawRequest("access-grants", patientAccessGrantListSchema);
}

/** A patient chooses the bounded read projections that a specific doctor may use. */
export function grantDoctorAccess(input: {
  doctorActorId: string;
  resourceScopes: readonly PatientGrantResource[];
  expiresAt: string;
}): Promise<PatientAccessGrantList> {
  return gerclawRequest("access-grants", patientAccessGrantListSchema, {
    method: "POST",
    body: JSON.stringify({
      doctor_actor_id: input.doctorActorId.trim(),
      resource_scopes: input.resourceScopes,
      expires_at: input.expiresAt,
    }),
  });
}

export function revokeDoctorAccess(input: {
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
