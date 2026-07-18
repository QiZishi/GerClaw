import { gerclawRequest } from "./client";
import { healthProfileSchema, type HealthProfile } from "./schemas";

function patientProfilePath(patientActorId: string): string {
  return `access-grants/patients/${encodeURIComponent(patientActorId.trim())}/health-profile`;
}

/** This projection is limited to the patient's currently confirmed health facts. */
export function readAuthorizedHealthProfile(patientActorId: string): Promise<HealthProfile> {
  return gerclawRequest(patientProfilePath(patientActorId), healthProfileSchema);
}
