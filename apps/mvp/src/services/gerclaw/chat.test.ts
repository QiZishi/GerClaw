import assert from "node:assert/strict";
import test from "node:test";

import { chatDoneEventSchema } from "./chat-contract.ts";
import {
  interruptedSchema,
  runDirectiveSchema,
} from "./chat-directive-contract.ts";
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

test("interrupted stream control is distinct from explicit cancellation", () => {
  assert.deepEqual(
    interruptedSchema.parse({
      trace_id: "trace_source_run_0001",
      status: "interrupted",
      message: "已按新要求调整执行。",
    }),
    {
      trace_id: "trace_source_run_0001",
      status: "interrupted",
      message: "已按新要求调整执行。",
    },
  );
  assert.equal(
    interruptedSchema.safeParse({
      trace_id: "trace_source_run_0001",
      status: "cancelled",
      message: "回答已停止。",
    }).success,
    false,
  );
});

test("run directive response excludes private worker identities", () => {
  const parsed = runDirectiveSchema.safeParse({
    schema_version: "1.0",
    id: "3d7e7c3d-95cc-46d7-ae91-c03c5bcbcc50",
    conversation_id: "2da90326-3490-4739-b7ab-274194bb2741",
    target_run_id: "08056df4-0f35-4c39-aac7-6e1c65b80cf4",
    successor_run_id: null,
    sequence: 2,
    mode: "queue_for_next_boundary",
    status: "pending",
    instruction: "下一步先回答饮食安排。",
    revision: 1,
    created_at: "2026-07-30T16:00:00Z",
    claimed_at: null,
    applied_at: null,
    cancelled_at: null,
  });
  assert.equal(parsed.success, true);
  assert.equal(
    runDirectiveSchema.safeParse({
      ...parsed.data,
      claimed_by_fencing_token: 9,
    }).success,
    false,
  );
});
