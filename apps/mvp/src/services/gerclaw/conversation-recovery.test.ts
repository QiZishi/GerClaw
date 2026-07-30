import assert from "node:assert/strict";
import test from "node:test";

import { planConversationRecovery } from "./conversation-recovery.ts";
import type { AgentRun, RunEventPage } from "./run-contract.ts";

const run = (status: AgentRun["status"]): AgentRun => ({
  schema_version: "1.1",
  id: "79d0809f-874a-4f1e-b2ab-02ec641a20ed",
  conversation_id: "db52e2be-b9a0-46af-9ed7-3d70a28e3dc0",
  input_message_id: "b0a9f396-e9f8-46fd-8529-f956dfd265bf",
  trace_id: "trace_recovery_12345678",
  route: "standard",
  status,
  current_answer_version_id:
    status === "completed" ? "7efbffe0-31d4-45eb-bc5e-89d40b2f774b" : null,
  warnings: [],
  last_sequence: status === "completed" ? 5 : 2,
  revision: status === "completed" ? 2 : 1,
  started_at: "2026-07-29T17:06:51.182497Z",
  interrupted_at:
    status === "interrupted" ? "2026-07-29T17:07:01.556369Z" : null,
  completed_at:
    status === "completed" ? "2026-07-29T17:07:04.556369Z" : null,
});

const replay: RunEventPage = {
  run_id: "79d0809f-874a-4f1e-b2ab-02ec641a20ed",
  events: [
    {
      schema_version: "1.0",
      run_id: "79d0809f-874a-4f1e-b2ab-02ec641a20ed",
      sequence: 1,
      event_type: "reasoning_summary",
      status: "running",
      public_summary: "正在分析",
      payload: {},
      duration_ms: null,
      created_at: "2026-07-29T17:06:51.203152Z",
    },
  ],
  next_after_sequence: 1,
};

test("history recovery replays a running Run from zero", () => {
  assert.deepEqual(planConversationRecovery(run("running"), replay), {
    action: "stream",
    mode: "attach",
    afterSequence: 0,
    publicSummaries: [],
  });
});

test("interrupted recovery keeps only bounded public summaries", () => {
  assert.deepEqual(planConversationRecovery(run("interrupted"), replay), {
    action: "stream",
    mode: "resume",
    afterSequence: 0,
    publicSummaries: ["正在分析"],
  });
});

test("a Run that completed during refresh reloads durable messages", () => {
  assert.deepEqual(planConversationRecovery(run("completed"), replay), {
    action: "refresh-history",
  });
});
