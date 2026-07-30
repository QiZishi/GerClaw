import assert from "node:assert/strict";
import test from "node:test";

import { skillEvolutionSchema } from "./schemas.ts";

const definition = {
  skill_id: "accessible-summary",
  name: "清晰摘要",
  description: "把已有内容整理成清晰短段落",
  version: "1.1.0",
  parameter_schema: {
    type: "object",
    properties: {},
    required: [],
    additionalProperties: false,
  },
  tool_names: [],
  category: "presentation",
  source: "custom",
  origin: "generated",
  enabled: true,
  revision: 2,
  created_at: "2026-07-30T08:00:00Z",
  updated_at: "2026-07-30T08:01:00Z",
  source_markdown: "---\nid: accessible-summary\n---\n# 工作流\n\n使用清晰短句。",
};

test("Skill evolution contract binds online activation to the resulting revision", () => {
  const parsed = skillEvolutionSchema.parse({
    trace_id: "trace_skill_evolution_0001",
    definition,
    quality_report: {
      version: "skill-draft-quality-v1",
      review_required: true,
      missing_checks: [],
    },
    decision: {
      schema_version: "skill-evolution-decision-v1",
      track: "mutable",
      object_kind: "skill.presentation",
      authority: "presentation_only",
      disposition: "online_applied",
      reason_codes: ["SKILL_PRESENTATION_DSL_ONLY"],
      expected_revision: 1,
      resulting_revision: 2,
    },
    active_definition: definition,
  });

  assert.equal(parsed.active_definition?.revision, 2);
});

test("Skill evolution contract rejects authority claims and inconsistent activation", () => {
  const base = {
    trace_id: "trace_skill_evolution_0002",
    definition: null,
    quality_report: null,
    decision: {
      schema_version: "skill-evolution-decision-v1",
      track: "immutable",
      object_kind: "skill.clinical",
      authority: "clinical_guidance",
      disposition: "offline_review_required",
      reason_codes: ["SKILL_CLINICAL_CONTENT"],
      expected_revision: 1,
      resulting_revision: null,
    },
    active_definition: null,
  };

  assert.equal(skillEvolutionSchema.safeParse(base).success, true);
  assert.equal(
    skillEvolutionSchema.safeParse({
      ...base,
      owner_verified: true,
      governance_authority: "presentation_only",
    }).success,
    false
  );
  assert.equal(
    skillEvolutionSchema.safeParse({
      ...base,
      decision: {
        ...base.decision,
        reason_codes: ["candidate contains clinical content"],
      },
    }).success,
    false
  );
  assert.equal(
    skillEvolutionSchema.safeParse({
      ...base,
      decision: {
        ...base.decision,
        track: "mutable",
        object_kind: "skill.presentation",
        authority: "presentation_only",
        disposition: "online_applied",
        resulting_revision: 2,
      },
      active_definition: null,
    }).success,
    false
  );
});
