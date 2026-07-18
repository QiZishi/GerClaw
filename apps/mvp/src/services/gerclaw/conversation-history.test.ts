import assert from "node:assert/strict";
import test from "node:test";

import { toFrontendSession } from "./conversation-session-presenter.ts";

test("marks a persisted prescription session for chat-native restore without exposing its content", () => {
  const session = toFrontendSession(
    {
      id: "2b14b0cd-4d0c-4c7f-a237-1fe195a9e101",
      title: null,
      has_prescription_draft: true,
      created_at: "2026-07-18T00:00:00Z",
      updated_at: "2026-07-18T00:05:00Z",
    },
    "patient",
  );

  assert.deepEqual(session, {
    id: "2b14b0cd-4d0c-4c7f-a237-1fe195a9e101",
    title: "五大处方计划",
    role: "patient",
    createdAt: Date.parse("2026-07-18T00:00:00Z"),
    updatedAt: Date.parse("2026-07-18T00:05:00Z"),
    messageCount: 0,
    panelType: "prescription",
  });
});
