import { gerclawRequest } from "./client";
import { riskAlertListSchema, type RiskAlert } from "./schemas";

export function listAuthorizedRiskAlerts(patientActorId: string): Promise<{ items: RiskAlert[] }> {
  return gerclawRequest(
    `access-grants/patients/${encodeURIComponent(patientActorId.trim())}/risk-alerts`,
    riskAlertListSchema,
  );
}
