import assert from "node:assert/strict";
import test from "node:test";

import { chatDoneEventSchema } from "./chat-contract.ts";
import {
  advanceDurableCursor,
  DurableStreamCursorError,
} from "./durable-stream.ts";

test("completion event accepts server-owned SSE observability metadata", () => {
  const parsed = chatDoneEventSchema.safeParse({
    full_text: "已完成的安全回复",
    references: [],
    trace_id: "trace_12345678",
    session_id: "6cf3c10d-1d9e-4cfb-8d42-1e32fdb92911",
    run_id: null,
    answer_group_run_id: null,
    answer_version_id: null,
    answer_version: null,
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
    run_id: null,
    answer_group_run_id: null,
    answer_version_id: null,
    answer_version: null,
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

test("completion event accepts a durable Run sequence cursor", () => {
  const parsed = chatDoneEventSchema.parse({
    full_text: "已完成的安全回复",
    references: [],
    trace_id: "trace_12345678",
    session_id: "6cf3c10d-1d9e-4cfb-8d42-1e32fdb92911",
    run_id: "5dd4df02-c17f-44fb-ad36-4da60cbb2dd7",
    answer_group_run_id: "5dd4df02-c17f-44fb-ad36-4da60cbb2dd7",
    answer_version_id: "11d8099d-50ba-413c-b683-b629bec33478",
    answer_version: 1,
    safety: {
      reviewed: true,
      disclaimer_applied: true,
      deterministic_diagnosis_blocked: false,
      high_risk_escalation_checked: true,
      notices: ["medical_disclaimer_applied"],
    },
    replayed: false,
    timestamp: 1_784_296_433.472992,
    sequence: 8,
  });

  assert.equal(parsed.sequence, 8);
});

test("durable cursor ignores duplicate replay and advances monotonically", () => {
  const cursor = { runId: undefined, lastSequence: 0 };
  assert.equal(
    advanceDurableCursor(
      {
        run_id: "5dd4df02-c17f-44fb-ad36-4da60cbb2dd7",
        sequence: 2,
      },
      cursor
    ),
    true
  );
  assert.equal(
    advanceDurableCursor(
      {
        run_id: "5dd4df02-c17f-44fb-ad36-4da60cbb2dd7",
        sequence: 2,
      },
      cursor
    ),
    false
  );
  assert.equal(cursor.lastSequence, 2);
});

test("durable cursor rejects partial or cross-Run metadata", () => {
  const cursor = {
    runId: "5dd4df02-c17f-44fb-ad36-4da60cbb2dd7",
    lastSequence: 2,
  };
  assert.throws(
    () => advanceDurableCursor({ sequence: 3 }, cursor),
    DurableStreamCursorError
  );
  assert.throws(
    () =>
      advanceDurableCursor(
        {
          run_id: "877315e7-f778-4669-b9bc-e43a579c6630",
          sequence: 3,
        },
        cursor
      ),
    DurableStreamCursorError
  );
});
