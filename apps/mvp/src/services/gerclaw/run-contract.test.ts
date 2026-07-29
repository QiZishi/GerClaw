import assert from "node:assert/strict";
import test from "node:test";

import {
  agentRunSchema,
  artifactWriteSchema,
  feedbackReconcileSchema,
  runEventPageSchema,
} from "./run-contract.ts";

const runId = "6cf3c10d-1d9e-4cfb-8d42-1e32fdb92911";
const conversationId = "8a3e70a1-8b3a-4a9b-9e6a-0148d6e1ef3b";
const messageId = "f177dc56-cf27-4c5f-8ebd-683d6a2d6e75";
const now = "2026-07-29T12:00:00Z";

test("Run contracts accept the versioned strict backend shape", () => {
  const run = agentRunSchema.parse({
    schema_version: "1.0",
    id: runId,
    conversation_id: conversationId,
    input_message_id: messageId,
    trace_id: "trace_contract_0001",
    route: "standard",
    status: "completed",
    current_answer_version_id: null,
    warnings: [],
    last_sequence: 2,
    revision: 2,
    started_at: now,
    completed_at: now,
  });
  const page = runEventPageSchema.parse({
    run_id: runId,
    events: [
      {
        schema_version: "1.0",
        run_id: runId,
        sequence: 2,
        event_type: "run.status",
        status: "completed",
        public_summary: "回答已完成",
        payload: {},
        duration_ms: null,
        created_at: now,
      },
    ],
    next_after_sequence: 2,
  });

  assert.equal(run.status, "completed");
  assert.equal(page.events[0].sequence, 2);
});

test("Run contracts reject extra fields, oversized payloads and invalid feedback", () => {
  const baseEvent = {
    schema_version: "1.0",
    run_id: runId,
    sequence: 1,
    event_type: "text_delta",
    status: "running",
    public_summary: null,
    duration_ms: null,
    created_at: now,
  };
  assert.equal(
    runEventPageSchema.safeParse({
      run_id: runId,
      events: [
        {
          ...baseEvent,
          payload: Object.fromEntries(
            Array.from({ length: 51 }, (_, index) => [`k${index}`, index])
          ),
        },
      ],
      next_after_sequence: 1,
    }).success,
    false
  );
  assert.equal(
    feedbackReconcileSchema.safeParse({ value: 2, expected_revision: 0 }).success,
    false
  );
  assert.equal(
    artifactWriteSchema.safeParse({
      title: "文档",
      markdown: "",
      unexpected: true,
    }).success,
    false
  );
});
