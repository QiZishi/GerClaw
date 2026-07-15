import { gerclawRequest } from "./client";
import {
  healthProfileSchema,
  memoryFactDecisionSchema,
  type HealthProfile,
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
