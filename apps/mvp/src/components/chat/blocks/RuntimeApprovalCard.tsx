"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Clock3, RefreshCw, ShieldAlert, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cancelRuntimeApproval, readRuntimeApproval } from "@/services/gerclaw/approvals";
import { GerclawApiError } from "@/services/gerclaw/client";
import { cn } from "@/lib/utils";
import { toast } from "@/components/ui/toast";
import { useAppStore } from "@/stores/appStore";
import type { RuntimeApprovalBlockData } from "@/types";

const statusCopy = {
  pending: "等待具备权限的工作人员确认",
  approved: "已获授权；后续执行将由受治理的工作流处理",
  rejected: "未获授权，操作没有执行",
  expired: "授权请求已过期，操作没有执行",
  cancelled: "您已取消本次授权请求",
} as const;

export function RuntimeApprovalCard({ data }: { data: RuntimeApprovalBlockData }) {
  const role = useAppStore((state) => state.role);
  const seniorMode = useAppStore((state) => state.seniorMode);
  const isSeniorPatient = role === "patient" && seniorMode;
  const [status, setStatus] = useState<keyof typeof statusCopy>("pending");
  const [revision, setRevision] = useState(1);
  const [requiredRoles, setRequiredRoles] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusConfirmed, setStatusConfirmed] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const requestVersion = useRef(0);

  const refresh = useCallback(async (announceFailure = true) => {
    const version = ++requestVersion.current;
    setLoading(true);
    setStatusConfirmed(false);
    setErrorMessage(null);
    try {
      const approval = await readRuntimeApproval(data.approvalId);
      if (version !== requestVersion.current) return;
      setStatus(approval.status);
      setRevision(approval.revision);
      setRequiredRoles(approval.required_roles);
      setStatusConfirmed(true);
    } catch (error) {
      if (version !== requestVersion.current) return;
      const message = error instanceof GerclawApiError ? error.message : "暂时无法读取授权状态";
      setErrorMessage(`${message}。当前状态未获服务端确认，操作不会自动执行。`);
      if (announceFailure) toast.show(message);
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, [data.approvalId]);

  useEffect(() => {
    let active = true;
    const version = ++requestVersion.current;
    void readRuntimeApproval(data.approvalId)
      .then((approval) => {
        if (!active || version !== requestVersion.current) return;
        setStatus(approval.status);
        setRevision(approval.revision);
        setRequiredRoles(approval.required_roles);
        setStatusConfirmed(true);
      })
      .catch((error) => {
        if (!active || version !== requestVersion.current) return;
        const message = error instanceof GerclawApiError ? error.message : "暂时无法读取授权状态";
        setErrorMessage(`${message}。当前状态未获服务端确认，操作不会自动执行。`);
      });
    return () => {
      active = false;
      if (requestVersion.current === version) requestVersion.current += 1;
    };
  }, [data.approvalId]);

  const cancel = async () => {
    const version = ++requestVersion.current;
    setLoading(true);
    setErrorMessage(null);
    try {
      const approval = await cancelRuntimeApproval({ id: data.approvalId, revision });
      if (version !== requestVersion.current) return;
      setStatus(approval.status);
      setRevision(approval.revision);
      setRequiredRoles(approval.required_roles);
      setStatusConfirmed(true);
      toast.show("已取消授权请求，操作没有执行");
    } catch (error) {
      if (version !== requestVersion.current) return;
      const message = error instanceof GerclawApiError ? error.message : "取消授权请求失败，请稍后重试";
      setErrorMessage(message);
      toast.show(message);
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  };

  const expiry = new Date(data.expiresAt);
  const expiryLabel = Number.isNaN(expiry.getTime())
    ? "有效期由服务端确认"
    : `将于 ${expiry.toLocaleString("zh-CN")} 失效`;

  return (
    <section
      className={cn(
        "w-full rounded-xl border border-amber-300 bg-amber-50/80 p-4 text-left text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-100",
        isSeniorPatient && "p-5 text-lg leading-8"
      )}
      aria-live="polite"
      aria-busy={loading}
    >
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 size-5 shrink-0" aria-hidden />
        <div className="min-w-0 flex-1 space-y-1">
          <h3 className="font-semibold">此操作需要人工授权</h3>
          <p>{statusConfirmed ? statusCopy[status] : "正在向服务端确认授权状态；确认前不会执行，也不能取消。"}</p>
          <p className={cn("text-xs opacity-80", isSeniorPatient && "text-base leading-7")}>
            涉及工具：{data.toolName}。为保护您的权益，系统已暂停该操作，且不会显示敏感参数。
          </p>
          <p className={cn("text-xs opacity-80", isSeniorPatient && "text-base leading-7")}>
            {expiryLabel} · 审核角色：{requiredRoles.length > 0 ? requiredRoles.join("、") : "正在向服务端确认"}
          </p>
          <p className={cn("text-[11px] opacity-70", isSeniorPatient && "text-base leading-7")}>
            策略版本 {data.policyVersion} · 工具版本 {data.toolVersion}
          </p>
        </div>
      </div>
      {errorMessage && (
        <p role="alert" className={cn("mt-3 rounded-lg border border-amber-400/70 bg-background/70 px-3 py-2 text-xs text-amber-950 dark:text-amber-100", isSeniorPatient && "px-4 py-3 text-base leading-7")}>
          {errorMessage}
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size={isSeniorPatient ? "default" : "sm"}
          onClick={() => void refresh()}
          disabled={loading}
          className={cn("gap-1.5", isSeniorPatient && "min-h-12 px-4 text-base")}
        >
          <RefreshCw className={cn("size-3.5", loading && "animate-spin")} />刷新状态
        </Button>
        {statusConfirmed && status === "pending" && (
          <Button
            type="button"
            variant="outline"
            size={isSeniorPatient ? "default" : "sm"}
            onClick={() => void cancel()}
            disabled={loading}
            className={cn("gap-1.5 border-amber-400", isSeniorPatient && "min-h-12 px-4 text-base")}
          >
            <XCircle className="size-3.5" />取消请求
          </Button>
        )}
        <span className={cn("inline-flex items-center gap-1 self-center text-xs opacity-80", isSeniorPatient && "min-h-12 text-base")}><Clock3 className="size-3.5" />不会自动执行</span>
      </div>
    </section>
  );
}
