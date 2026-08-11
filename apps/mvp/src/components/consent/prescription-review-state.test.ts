import assert from "node:assert/strict";
import test from "node:test";

import { prescriptionReviewPresentation } from "./prescription-review-state.ts";
import type { PrescriptionDraftReview } from "@/services/gerclaw/schemas";

function review(
  revision: number,
  decision: "approved" | "returned",
  amendedMarkdown: string | null = null,
): PrescriptionDraftReview {
  return {
    review_id: `${revision}`.padStart(8, "0") + "-1111-4111-8111-111111111111",
    draft_id: "22222222-2222-4222-8222-222222222222",
    doctor_actor_id: "usr_account_11111111111111111111111111111111",
    decision,
    review_note: `第 ${revision} 次意见`,
    amended_markdown: amendedMarkdown,
    amendment_evidence_ids: amendedMarkdown ? ["ev_local1234"] : [],
    revision,
    reviewed_at: `2026-08-${String(revision).padStart(2, "0")}T08:00:00.000Z`,
  };
}

test("an untouched model draft remains pending review", () => {
  assert.deepEqual(prescriptionReviewPresentation([]), {
    status: "pending",
    label: "待复核",
    latestReview: null,
    latestAmendment: null,
  });
});

test("the highest review revision controls the visible status", () => {
  const first = review(1, "approved", "# 第一版医生修订");
  const latest = review(3, "returned");
  const result = prescriptionReviewPresentation([first, latest, review(2, "approved")]);
  assert.equal(result.status, "returned");
  assert.equal(result.label, "已退回");
  assert.equal(result.latestReview, latest);
  assert.equal(result.latestAmendment, first);
});

test("the latest amendment is separate from the model draft status", () => {
  const older = review(2, "returned", "# 旧修订");
  const latest = review(4, "approved", "# 最新医生修订");
  const result = prescriptionReviewPresentation([latest, older]);
  assert.equal(result.status, "approved");
  assert.equal(result.latestAmendment?.amended_markdown, "# 最新医生修订");
});
