import assert from "node:assert/strict";
import test from "node:test";

import { buildFeedbackPayload } from "./feedback-contract.ts";

const traceId = "trace_feedback_000000000000000000000001";
const idempotencyKey = "idem_feedback_000000000000000000000001";

test("feedback payload keeps comments optional and trims submitted text", () => {
  assert.deepEqual(
    buildFeedbackPayload({
      idempotencyKey,
      traceId,
      rating: "positive",
      comment: "  内容清楚  ",
    }),
    {
      idempotency_key: idempotencyKey,
      trace_id: traceId,
      rating: "positive",
      categories: [],
      comment: "内容清楚",
      metadata: {},
    }
  );
  assert.equal(
    "comment" in buildFeedbackPayload({
      idempotencyKey,
      traceId,
      rating: "negative",
      comment: "  ",
    }),
    false
  );
});

test("feedback payload rejects malformed trace ids, keys and oversized comments", () => {
  assert.throws(
    () => buildFeedbackPayload({ idempotencyKey, traceId: "trace_bad", rating: "positive" }),
    /Invalid/
  );
  assert.throws(
    () => buildFeedbackPayload({ idempotencyKey: "idem_bad", traceId, rating: "positive" }),
    /Invalid/
  );
  assert.throws(
    () => buildFeedbackPayload({ idempotencyKey, traceId, rating: "positive", comment: "x".repeat(2_001) }),
    /Too big/
  );
});
