import { z } from "zod";
import { gerclawRequest } from "./client";
import {
  memoryFactCreateInputSchema,
  memoryFactDeleteInputSchema,
  healthProfileSchema,
  memoryFactDecisionSchema,
  memoryFactHistorySchema,
  memoryFactMutationSchema,
  memoryFactRestoreInputSchema,
  memoryFactUpdateInputSchema,
  memoryRecallPreferenceSchema,
  type CreateMemoryFactInput,
  type UpdateMemoryFactInput,
  type HealthProfile,
  type MemoryFactHistory,
} from "./schemas";

export function readHealthProfile(): Promise<HealthProfile> {
  return gerclawRequest("memory/profile", healthProfileSchema);
}

export function updateMemoryRecallPreference(
  expectedProfileVersion: number,
  enabled: boolean
) {
  return gerclawRequest(
    "memory/profile/recall",
    memoryRecallPreferenceSchema,
    {
      method: "PATCH",
      body: JSON.stringify({
        expected_profile_version: expectedProfileVersion,
        enabled,
      }),
    }
  );
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

export function createMemoryFact(input: CreateMemoryFactInput) {
  const parsed = memoryFactCreateInputSchema.parse(input);
  return gerclawRequest("memory/facts", memoryFactMutationSchema, {
    method: "POST",
    body: JSON.stringify(parsed),
  });
}

export function updateMemoryFact(
  factId: string,
  input: UpdateMemoryFactInput
) {
  const parsedFactId = z.string().uuid().parse(factId);
  const parsed = memoryFactUpdateInputSchema.parse(input);
  return gerclawRequest(
    `memory/facts/${encodeURIComponent(parsedFactId)}`,
    memoryFactMutationSchema,
    { method: "PATCH", body: JSON.stringify(parsed) }
  );
}

export function deleteMemoryFact(
  factId: string,
  expectedRevision: number,
  reason: "user_deleted" | "outdated" | "incorrect" | "duplicate" = "user_deleted"
) {
  const parsedFactId = z.string().uuid().parse(factId);
  const payload = memoryFactDeleteInputSchema.parse({
    expected_revision: expectedRevision,
    reason,
  });
  return gerclawRequest(
    `memory/facts/${encodeURIComponent(parsedFactId)}`,
    memoryFactMutationSchema,
    {
      method: "DELETE",
      body: JSON.stringify(payload),
    }
  );
}

export function restoreMemoryFact(factId: string, expectedRevision: number) {
  const parsedFactId = z.string().uuid().parse(factId);
  const payload = memoryFactRestoreInputSchema.parse({
    expected_revision: expectedRevision,
  });
  return gerclawRequest(
    `memory/facts/${encodeURIComponent(parsedFactId)}/restore`,
    memoryFactMutationSchema,
    {
      method: "POST",
      body: JSON.stringify(payload),
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
