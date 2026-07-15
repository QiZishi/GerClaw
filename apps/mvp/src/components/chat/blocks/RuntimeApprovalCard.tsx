"use client";

import { useState } from "react";
import { Clock3, RefreshCw, ShieldAlert, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cancelRuntimeApproval, readRuntimeApproval } from "@/services/gerclaw/approvals";
import { GerclawApiError } from "@/services/gerclaw/client";
import { cn } from "@/lib/utils";
import { toast } from "@/components/ui/toast";
import type { RuntimeApprovalBlockData } from "@/types";

const statusCopy = {
  pending: "等待具备权限的工作人员确认",
  approved: "已获授权；后续执行将由受治理的工作流处理",
  rejected: "未获授权，操作没有执行",
  expired: "授权请求已过期，操作没有执行",
  cancelled: "您已取消本次授权请求",
} as const;

export function RuntimeApprovalCard({ data }: { data: RuntimeApprovalBlockData }) {
  const [status, setStatus] = useState<keyof typeof statusCopy>("pending");
  const [revision, setRevision] = useState(1);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const approval = await readRuntimeApproval(data.approvalId);
      setStatus(approval.status);
      setRevision(approval.revision);
    } catch (error) {
      toast.show(error instanceof GerclawApiError ? error.message : "暂时无法读取授权状态");
    } finally {
      setLoading(false);
    }
  };

  const cancel = async () => {
    setLoading(true);
    try {
      const approval = await cancelRuntimeApproval({ id: data.approvalId, revision });
      setStatus(approval.status);
      setRevision(approval.revision);
      toast.show("已取消授权请求，操作没有执行");
    } catch (error) {
      toast.show(error instanceof GerclawApiError ? error.message : "取消授权请求失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="w-full rounded-xl border border-amber-300 bg-amber-50/80 p-4 text-left text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-100" aria-live="polite">
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 size-5 shrink-0" aria-hidden />
        <div className="min-w-0 flex-1 space-y-1">
          <h3 className="font-semibold">此操作需要人工授权</h3>
          <p>{statusCopy[status]}</p>
          <p className="text-xs opacity-80">涉及工具：{data.toolName} · 将于 {new Date(data.expiresAt).toLocaleString("zh-CN")} 失效</p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => void refresh()} disabled={loading} className="gap-1.5">
          <RefreshCw className={cn("size-3.5", loading && "animate-spin")} />刷新状态
        </Button>
        {status === "pending" && (
          <Button type="button" variant="outline" size="sm" onClick={() => void cancel()} disabled={loading} className="gap-1.5 border-amber-400">
            <XCircle className="size-3.5" />取消请求
          </Button>
        )}
        <span className="inline-flex items-center gap-1 self-center text-xs opacity-80"><Clock3 className="size-3.5" />不会自动执行</span>
      </div>
    </section>
  );
}
