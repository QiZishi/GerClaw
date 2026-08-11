import type { PrescriptionDraftReview } from "@/services/gerclaw/schemas";

export type PrescriptionReviewStatus = "pending" | "approved" | "returned";

export interface PrescriptionReviewPresentation {
  status: PrescriptionReviewStatus;
  label: "待复核" | "已通过" | "已退回";
  latestReview: PrescriptionDraftReview | null;
  latestAmendment: PrescriptionDraftReview | null;
}

function newestReview(reviews: readonly PrescriptionDraftReview[]) {
  return reviews.reduce<PrescriptionDraftReview | null>(
    (latest, review) => !latest || review.revision > latest.revision ? review : latest,
    null,
  );
}

export function prescriptionReviewPresentation(
  reviews: readonly PrescriptionDraftReview[],
): PrescriptionReviewPresentation {
  const latestReview = newestReview(reviews);
  const latestAmendment = newestReview(
    reviews.filter((review) => Boolean(review.amended_markdown)),
  );
  if (!latestReview) {
    return { status: "pending", label: "待复核", latestReview: null, latestAmendment };
  }
  return {
    status: latestReview.decision,
    label: latestReview.decision === "approved" ? "已通过" : "已退回",
    latestReview,
    latestAmendment,
  };
}
