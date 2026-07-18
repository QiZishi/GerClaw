import { gerclawRequest } from "./client";
import {
  doctorChronicCareConditionDetailSchema,
  doctorChronicCareConditionListSchema,
  type DoctorChronicCareConditionDetail,
  type DoctorChronicCareConditionList,
} from "./schemas";

function chronicCarePath(patientActorId: string): string {
  return `access-grants/patients/${encodeURIComponent(patientActorId.trim())}/chronic-care`;
}

/** A doctor may read only the narrow ledger projection explicitly granted by the patient. */
export function listAuthorizedChronicCareConditions(
  patientActorId: string,
): Promise<DoctorChronicCareConditionList> {
  return gerclawRequest(chronicCarePath(patientActorId), doctorChronicCareConditionListSchema);
}

export function getAuthorizedChronicCareCondition(input: {
  patientActorId: string;
  conditionId: string;
}): Promise<DoctorChronicCareConditionDetail> {
  return gerclawRequest(
    `${chronicCarePath(input.patientActorId)}/conditions/${encodeURIComponent(input.conditionId)}`,
    doctorChronicCareConditionDetailSchema,
  );
}
