import assert from "node:assert/strict";
import test from "node:test";

import { chatDoneEventSchema } from "./chat-contract.ts";

test("completion event accepts server-owned SSE observability metadata", () => {
  const parsed = chatDoneEventSchema.safeParse({
    full_text: "已完成的安全回复",
    references: [],
    trace_id: "trace_12345678",
    session_id: "6cf3c10d-1d9e-4cfb-8d42-1e32fdb92911",
    safety: {
      reviewed: true,
      disclaimer_applied: true,
      deterministic_diagnosis_blocked: false,
      high_risk_escalation_checked: true,
      notices: ["medical_disclaimer_applied"],
    },
    replayed: false,
    timestamp: 1_784_296_433.472992,
  });

  assert.equal(parsed.success, true);
});

test("completion event rejects undeclared transport fields", () => {
  const parsed = chatDoneEventSchema.safeParse({
    full_text: "已完成的安全回复",
    references: [],
    trace_id: "trace_12345678",
    session_id: "6cf3c10d-1d9e-4cfb-8d42-1e32fdb92911",
    safety: {
      reviewed: true,
      disclaimer_applied: true,
      deterministic_diagnosis_blocked: false,
      high_risk_escalation_checked: true,
      notices: ["medical_disclaimer_applied"],
    },
    replayed: false,
    timestamp: 1_784_296_433.472992,
    unexpected: "contract drift",
  });

  assert.equal(parsed.success, false);
});
