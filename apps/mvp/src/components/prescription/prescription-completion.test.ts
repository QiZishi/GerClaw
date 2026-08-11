import assert from "node:assert/strict";
import test from "node:test";

import {
  prepareManualPrescriptionAnswers,
  prescriptionMissingFields,
  prescriptionTurnProgress,
} from "./prescription-completion.ts";

const fields = [
  { id: "goals", label: "健康目标", max_length: 20 },
  { id: "history", label: "病史", max_length: 30 },
];

test("prescription turn progress stops exactly at the configured limit", () => {
  assert.deepEqual(prescriptionTurnProgress(4, 5), {
    completed: 4,
    remaining: 1,
    limitReached: false,
  });
  assert.deepEqual(prescriptionTurnProgress(5, 5), {
    completed: 5,
    remaining: 0,
    limitReached: true,
  });
});

test("manual completion uses only server-declared missing fields", () => {
  assert.deepEqual(prescriptionMissingFields(fields, ["history"]), [fields[1]]);
});

test("manual completion trims values and focuses the first blank field", () => {
  assert.deepEqual(
    prepareManualPrescriptionAnswers(fields, { goals: "  安全活动  ", history: " " }),
    {
      answers: { goals: "安全活动" },
      firstMissingFieldId: "history",
    },
  );
});
