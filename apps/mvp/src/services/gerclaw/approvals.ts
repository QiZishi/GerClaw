import { z } from "zod";
import { gerclawRequest } from "./client";
import {
  approvalGrantSchema,
  approvalReviewSchema,
  approvalSchema,
  type RuntimeApproval,
  type RuntimeApprovalReview,
} from "./schemas";

const cancellationSchema = z
  .object({ expected_revision: z.number().int().positive(), reason: z.string().min(2).max(1_000) })
  .strict();

const decisionSchema = z
  .object({
    expected_revision: z.number().int().positive(),
    decision: z.enum(["approved", "rejected"]),
    reason: z.string().trim().min(2).max(1_000),
  })
  .strict();

export function readRuntimeApproval(approvalId: string): Promise<RuntimeApproval> {
  return gerclawRequest(`runtime/approvals/${approvalId}`, approvalSchema);
}

export function cancelRuntimeApproval(
  approval: Pick<RuntimeApproval, "id" | "revision">
): Promise<RuntimeApproval> {
  return gerclawRequest(
    `runtime/approvals/${approval.id}/cancel`,
    approvalSchema,
    {
      method: "POST",
      body: JSON.stringify(
        cancellationSchema.parse({
          expected_revision: approval.revision,
          reason: "请求人已取消本次操作",
        })
      ),
    }
  );
}

/** Read encrypted arguments only after the API verifies the active approver role. */
export function reviewRuntimeApproval(approvalId: string): Promise<RuntimeApprovalReview> {
  return gerclawRequest(
    `runtime/approvals/${encodeURIComponent(approvalId)}/review`,
    approvalReviewSchema
  );
}

/**
 * Persist an authorized decision. The one-time server execution credential is
 * intentionally discarded in the browser: this UI records a human decision,
 * it does not execute a side effect.
 */
export async function decideRuntimeApproval(input: {
  approval: Pick<RuntimeApproval, "id" | "revision">;
  decision: "approved" | "rejected";
  reason: string;
}): Promise<RuntimeApproval> {
  const result = await gerclawRequest(
    `runtime/approvals/${encodeURIComponent(input.approval.id)}/decision`,
    approvalGrantSchema,
    {
      method: "POST",
      body: JSON.stringify(
        decisionSchema.parse({
          expected_revision: input.approval.revision,
          decision: input.decision,
          reason: input.reason,
        })
      ),
    }
  );
  return result.approval;
}
