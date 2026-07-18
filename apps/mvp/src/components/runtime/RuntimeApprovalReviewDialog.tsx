"use client";

import { useState } from "react";
import { Check, ShieldCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { InlineLoadingState } from "@/components/ui/inline-loading-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { decideRuntimeApproval, reviewRuntimeApproval } from "@/services/gerclaw/approvals";
import type { RuntimeApprovalReview } from "@/services/gerclaw/schemas";

const approvalIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const statusLabel = {
  pending: "待审核",
  approved: "已批准",
  rejected: "已退回",
  expired: "已过期",
  cancelled: "已取消",
} as const;

export function RuntimeApprovalReviewDialog({
  open,
  onOpenChange,
  seniorMode,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  seniorMode: boolean;
}) {
  const [approvalId, setApprovalId] = useState("");
  const [review, setReview] = useState<RuntimeApprovalReview | null>(null);
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [deciding, setDeciding] = useState<"approved" | "rejected" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const textClass = seniorMode ? "text-lg leading-8" : "text-sm leading-6";

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
    setApprovalId("");
    setReview(null);
    setReason("");
    setLoading(false);
    setDeciding(null);
    setError(null);
    }
    onOpenChange(nextOpen);
  }

  async function loadReview() {
    if (loading || !approvalIdPattern.test(approvalId.trim())) return;
    setLoading(true);
    setError(null);
    try {
      setReview(await reviewRuntimeApproval(approvalId.trim()));
    } catch {
      setReview(null);
      setError("未找到可审核的授权，或当前账户没有审核权限。");
    } finally {
      setLoading(false);
    }
  }

  async function decide(decision: "approved" | "rejected") {
    if (!review || review.approval.status !== "pending" || reason.trim().length < 2 || deciding) return;
    setDeciding(decision);
    setError(null);
    try {
      const approval = await decideRuntimeApproval({
        approval: review.approval,
        decision,
        reason: reason.trim(),
      });
      setReview((current) => current && { ...current, approval });
      setReason("");
    } catch {
      setError("审核决定未保存，请刷新授权编号后重试。");
    } finally {
      setDeciding(null);
    }
  }

  const approval = review?.approval;
  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className={cn("max-h-[90vh] overflow-y-auto sm:max-w-2xl", seniorMode && "p-5")} showCloseButton={!seniorMode}>
        <DialogHeader>
          <div className="mb-1 flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <ShieldCheck className="size-5" aria-hidden />
          </div>
          <DialogTitle className={cn(seniorMode && "text-2xl")}>操作授权复核</DialogTitle>
          <DialogDescription className={textClass}>输入患者提供的授权编号。</DialogDescription>
        </DialogHeader>
        <div className="mt-2 flex gap-2">
          <div className="min-w-0 flex-1">
            <Label htmlFor="runtime-approval-id" className="sr-only">授权编号</Label>
            <Input
              id="runtime-approval-id"
              value={approvalId}
              onChange={(event) => setApprovalId(event.target.value.trim())}
              placeholder="授权编号"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              maxLength={36}
              className={cn("font-mono", seniorMode && "h-12 text-base")}
            />
          </div>
          <Button type="button" onClick={() => void loadReview()} disabled={loading || !approvalIdPattern.test(approvalId)} className={cn(seniorMode && "min-h-12 text-lg")}>读取</Button>
        </div>
        {loading && <InlineLoadingState message="正在读取授权" className="min-h-24" />}
        {error && <p role="alert" className={cn("rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive", textClass)}>{error}</p>}
        {approval && !loading && <section className="space-y-4 rounded-xl border p-4" aria-label="授权详情">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className={cn("font-semibold", seniorMode && "text-xl")}>{approval.tool_name}</h3>
            <span className={cn("rounded-full bg-muted px-2 py-1 text-xs", seniorMode && "text-base")}>{statusLabel[approval.status]}</span>
          </div>
          <dl className={cn("grid gap-2", textClass)}>
            <div><dt className="text-muted-foreground">工具版本</dt><dd>{approval.tool_version}</dd></div>
            <div><dt className="text-muted-foreground">审核角色</dt><dd>{approval.required_roles.join("、")}</dd></div>
            <div><dt className="text-muted-foreground">失效时间</dt><dd>{new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(approval.expires_at))}</dd></div>
          </dl>
          <details className={textClass}>
            <summary className="cursor-pointer font-medium">查看本次操作内容</summary>
            <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-muted/60 p-3 text-xs leading-5">{JSON.stringify(review.arguments, null, 2)}</pre>
          </details>
          {approval.status === "pending" && <div className="grid gap-2 border-t pt-4">
            <Label htmlFor="runtime-approval-reason" className={cn(seniorMode && "text-lg")}>复核意见</Label>
            <textarea
              id="runtime-approval-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value.slice(0, 1_000))}
              maxLength={1_000}
              className={cn("min-h-24 rounded-md border border-input bg-background p-3", seniorMode && "min-h-32 text-lg")}
            />
            <DialogFooter className={cn("gap-2", seniorMode && "flex-row justify-end gap-3")}>
              <Button type="button" variant="outline" disabled={reason.trim().length < 2 || deciding !== null} onClick={() => void decide("rejected")} className={cn(seniorMode && "min-h-12 text-lg")}><X className="size-4" />退回</Button>
              <Button type="button" disabled={reason.trim().length < 2 || deciding !== null} onClick={() => void decide("approved")} className={cn(seniorMode && "min-h-12 text-lg")}><Check className="size-4" />{deciding === "approved" ? "正在保存…" : "记录批准"}</Button>
            </DialogFooter>
          </div>}
        </section>}
      </DialogContent>
    </Dialog>
  );
}
