import { gerclawRequest } from "./client";
import { riskAlertListSchema, riskAlertSchema, type RiskAlert } from "./schemas";

export function listRiskAlerts(): Promise<{ items: RiskAlert[] }> {
  return gerclawRequest("risk-alerts", riskAlertListSchema);
}

export function acknowledgeRiskAlert(alert: RiskAlert, idempotencyKey: string): Promise<RiskAlert> {
  return gerclawRequest(
    `risk-alerts/${encodeURIComponent(alert.alert_id)}/acknowledgements`,
    riskAlertSchema,
    {
      method: "POST",
      body: JSON.stringify({ expected_revision: alert.revision, idempotency_key: idempotencyKey }),
    }
  );
}
