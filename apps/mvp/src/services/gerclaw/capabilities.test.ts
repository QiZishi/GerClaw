import assert from "node:assert/strict";
import test from "node:test";

import { capabilityCatalogSchema } from "./capabilities-contract.ts";

const manifest = {
  schema_version: "1.0",
  capability_id: "gerclaw.cga",
  version: "1.0.0",
  display_name: "老年综合评估",
  risk_level: "medium",
  owner_module: "cga",
  entrypoint: "cga_assessment",
  automatic_selection: true,
  manual_selection: true,
  supported_workflows: ["standard", "cga"],
  required_tools: [],
  shared_result_kinds: ["clinical_observation"],
  input_schema: { type: "object", additionalProperties: false },
  output_schema: { type: "object", required: ["assessment_id", "status"] },
};

test("capability catalog accepts the strict versioned public contract", () => {
  const result = capabilityCatalogSchema.parse({ capabilities: [manifest] });
  assert.equal(result.capabilities[0].owner_module, "cga");
});

test("capability catalog rejects owner boundary drift and extra response keys", () => {
  assert.equal(
    capabilityCatalogSchema.safeParse({
      capabilities: [{ ...manifest, entrypoint: "python_import" }],
    }).success,
    false
  );
  assert.equal(
    capabilityCatalogSchema.safeParse({
      capabilities: [{ ...manifest, private_prompt: "do not expose" }],
    }).success,
    false
  );
});
