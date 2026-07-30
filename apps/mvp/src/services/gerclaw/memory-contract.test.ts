import assert from "node:assert/strict";
import test from "node:test";
import {
  memoryFactCreateInputSchema,
  memoryFactHistorySchema,
  memoryFactMutationSchema,
} from "./memory-contract.ts";

const fact = {
  id: "e7f234c4-50cb-4c6f-b556-05cc840912c0",
  category: "allergy",
  memory_type: "stable",
  status: "inactive",
  access_level: "standard",
  statement: "我对青霉素过敏",
  details: { entity: "青霉素", source: "user_explicit_create" },
  confidence: 1,
  revision: 2,
  source_trace_id: "trace_memory_contract_0001",
  occurred_at: null,
  confirmed_at: null,
  expires_at: null,
  tombstoned_at: "2026-07-30T06:00:00Z",
  tombstone_reason: "incorrect",
  can_restore: true,
  updated_at: "2026-07-30T06:00:00Z",
  relevance_score: null,
};

test("memory mutation contract requires an explicit restorable tombstone state", () => {
  const parsed = memoryFactMutationSchema.parse({
    fact,
    profile_version: 3,
  });
  assert.equal(parsed.fact.can_restore, true);
  assert.equal(parsed.fact.tombstone_reason, "incorrect");

  const withoutRestoreState = { ...fact };
  delete (withoutRestoreState as Partial<typeof fact>).can_restore;
  assert.equal(
    memoryFactMutationSchema.safeParse({
      fact: withoutRestoreState,
      profile_version: 3,
    }).success,
    false
  );
  assert.equal(
    memoryFactCreateInputSchema.safeParse({
      expected_profile_version: 0,
      category: "vital_sign",
      memory_type: "evolving",
      entity: "血压",
      statement: "我的血压是130/80 mmHg",
      details: { value: " ", unit: " " },
    }).success,
    false
  );
});

test("memory history contract preserves mutation activity and rejects extra control data", () => {
  const item = {
    revision: 1,
    activity: "user_delete",
    category: "allergy",
    memory_type: "stable",
    status: "confirmed",
    access_level: "standard",
    statement: "我对青霉素过敏",
    details: { entity: "青霉素" },
    confidence: 1,
    source_trace_id: "trace_memory_contract_0001",
    occurred_at: null,
    confirmed_at: "2026-07-30T05:00:00Z",
    expires_at: null,
    tombstoned_at: null,
    tombstone_reason: null,
    updated_at: "2026-07-30T05:00:00Z",
    recorded_at: "2026-07-30T06:00:00Z",
  };
  assert.equal(
    memoryFactHistorySchema.safeParse({ fact_id: fact.id, items: [item] }).success,
    true
  );
  assert.equal(
    memoryFactHistorySchema.safeParse({
      fact_id: fact.id,
      items: [{ ...item, governance_authority: "control_plane" }],
    }).success,
    false
  );
});

test("memory write input cannot self-declare governance authority or ownership", () => {
  assert.equal(
    memoryFactCreateInputSchema.safeParse({
      expected_profile_version: 0,
      category: "preference",
      memory_type: "evolving",
      entity: "回答风格",
      statement: "请使用简洁回答",
      governance_authority: "control_plane",
      owner_verified: true,
    }).success,
    false
  );
  assert.equal(
    memoryFactCreateInputSchema.safeParse({
      expected_profile_version: 0,
      category: "vital_sign",
      memory_type: "evolving",
      entity: "血压",
      statement: "我的血压记录需要清空",
      details: { value: null, unit: null },
    }).success,
    false
  );
});
