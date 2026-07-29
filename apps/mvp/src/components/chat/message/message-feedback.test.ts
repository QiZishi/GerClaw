import assert from "node:assert/strict";
import test from "node:test";

import { feedbackValueToMessage, nextFeedbackValue } from "./message-feedback.ts";

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
