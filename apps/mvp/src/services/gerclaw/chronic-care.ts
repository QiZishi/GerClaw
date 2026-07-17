import { gerclawRequest } from "./client";
import {
  chronicConditionListSchema,
  chronicConditionSchema,
  chronicMeasurementListSchema,
  chronicMeasurementSchema,
  chronicTrendListSchema,
  type ChronicCondition,
  type ChronicMeasurement,
  type ChronicTrend,
} from "./schemas";

export function listChronicConditions(): Promise<{ items: ChronicCondition[] }> {
  return gerclawRequest("chronic-care/conditions", chronicConditionListSchema);
}

export function createChronicCondition(label: string): Promise<ChronicCondition> {
  return gerclawRequest("chronic-care/conditions", chronicConditionSchema, {
    method: "POST",
    body: JSON.stringify({ label }),
  });
}

export function addChronicMeasurement(
  conditionId: string,
  input: { metric_label: string; value: number; unit: string; measured_at: string }
): Promise<ChronicMeasurement> {
  return gerclawRequest(
    `chronic-care/conditions/${encodeURIComponent(conditionId)}/measurements`,
    chronicMeasurementSchema,
    { method: "POST", body: JSON.stringify(input) }
  );
}

export function listChronicMeasurements(
  conditionId: string
): Promise<{ items: ChronicMeasurement[] }> {
  return gerclawRequest(
    `chronic-care/conditions/${encodeURIComponent(conditionId)}/measurements`,
    chronicMeasurementListSchema
  );
}

export function listChronicTrends(conditionId: string): Promise<{ items: ChronicTrend[] }> {
  return gerclawRequest(
    `chronic-care/conditions/${encodeURIComponent(conditionId)}/trends`,
    chronicTrendListSchema
  );
}
