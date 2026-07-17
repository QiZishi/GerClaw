import { z } from "zod";
import { gerclawRequest } from "./client";
import {
  healthProfileSchema,
  memoryFactDecisionSchema,
  memoryFactHistorySchema,
  type HealthProfile,
  type MemoryFactHistory,
} from "./schemas";

export function readHealthProfile(): Promise<HealthProfile> {
  return gerclawRequest("memory/profile", healthProfileSchema);
}

export function decideMemoryFact(
  factId: string,
  expectedRevision: number,
  decision: "confirm" | "reject"
) {
  return gerclawRequest(
    `memory/facts/${factId}/decision`,
    memoryFactDecisionSchema,
    {
      method: "POST",
      body: JSON.stringify({ expected_revision: expectedRevision, decision }),
    }
  );
}

export function readMemoryFactHistory(factId: string): Promise<MemoryFactHistory> {
  const parsedFactId = z.string().uuid().parse(factId);
  return gerclawRequest(
    `memory/facts/${encodeURIComponent(parsedFactId)}/history`,
    memoryFactHistorySchema
  );
}
