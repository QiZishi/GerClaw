import { z } from "zod";
import { gerclawRequest } from "./client";
import { approvalSchema, type RuntimeApproval } from "./schemas";

const cancellationSchema = z
  .object({ expected_revision: z.number().int().positive(), reason: z.string().min(2).max(1_000) })
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
