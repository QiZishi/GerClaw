import { gerclawRequest } from "./client";
import { cgaHistorySchema, type CgaHistoryItem } from "./schemas";

function patientCgaPath(patientActorId: string): string {
  return `access-grants/patients/${encodeURIComponent(patientActorId.trim())}/cga-reports`;
}

/** Completed screening summaries only; the API never exposes answers or active assessments. */
export function listAuthorizedCgaReports(patientActorId: string): Promise<{ items: CgaHistoryItem[] }> {
  return gerclawRequest(patientCgaPath(patientActorId), cgaHistorySchema);
}
