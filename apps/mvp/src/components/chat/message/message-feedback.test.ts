import assert from "node:assert/strict";
import test from "node:test";

import {
  feedbackValueToMessage,
  nextFeedbackValue,
  planMessageFeedbackClick,
} from "./message-feedback.ts";

test("run feedback is a current value and clicking the selected value clears it", () => {
  assert.equal(nextFeedbackValue(null, "up"), 1);
  assert.equal(nextFeedbackValue("up", "up"), 0);
  assert.equal(nextFeedbackValue("down", "up"), 1);
  assert.equal(nextFeedbackValue("down", "down"), 0);
});

test("server feedback values map to visible message state", () => {
  assert.equal(feedbackValueToMessage(1), "up");
  assert.equal(feedbackValueToMessage(-1), "down");
  assert.equal(feedbackValueToMessage(0), null);
});

test("the first trace-backed rating opens the optional comment dialog", () => {
  assert.equal(planMessageFeedbackClick(null, true, true), "open-dialog");
  assert.equal(planMessageFeedbackClick(null, false, true), "open-dialog");
});

test("existing run ratings reconcile directly while legacy ratings stay immutable", () => {
  assert.equal(planMessageFeedbackClick("up", true, true), "reconcile");
  assert.equal(planMessageFeedbackClick("down", true, false), "reconcile");
  assert.equal(planMessageFeedbackClick("up", false, true), "ignore");
  assert.equal(planMessageFeedbackClick(null, false, false), "ignore");
});
