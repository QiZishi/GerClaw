"use client";

import { type FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InlineLoadingState } from "@/components/ui/inline-loading-state";
import { cn } from "@/lib/utils";
import {
  grantPrescriptionReviewAccess,
  listPrescriptionReviewGrants,
  revokePrescriptionReviewAccess,
} from "@/services/gerclaw/consent";
import type { PatientAccessGrant } from "@/services/gerclaw/schemas";

const doctorActorIdPattern = /^usr_account_[a-f0-9]{32}$/;

function expiryAfter(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString();
}

function displayExpiry(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium" }).format(new Date(value));
}

export function PrescriptionReviewAccessDialog({
  open,
  onOpenChange,
  seniorMode,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  seniorMode: boolean;
}) {
  const [grants, setGrants] = useState<PatientAccessGrant[]>([]);
  const [doctorActorId, setDoctorActorId] = useState("");
  const [expiryDays, setExpiryDays] = useState(90);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textClass = seniorMode ? "text-lg leading-8" : "text-sm leading-6";

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const response = await listPrescriptionReviewGrants();
      setGrants(response.items.filter((item) => item.resource_scope === "prescription_draft_review"));
    } catch {
      setError("暂时无法读取授权记录，请稍后重试。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [open]);

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      setDoctorActorId("");
      setError(null);
    }
    onOpenChange(nextOpen);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !doctorActorIdPattern.test(doctorActorId.trim())) return;
    setPending(true);
    setError(null);
    try {
      const response = await grantPrescriptionReviewAccess({
        doctorActorId,
        expiresAt: expiryAfter(expiryDays),
      });
      setGrants(response.items.filter((item) => item.resource_scope === "prescription_draft_review"));
      setDoctorActorId("");
    } catch {
      setError("授权未保存，请核对医生复核代码后重试。");
    } finally {
      setPending(false);
    }
  }

  async function revoke(grant: PatientAccessGrant) {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      const updated = await revokePrescriptionReviewAccess({
        grantId: grant.id,
        expectedRevision: grant.revision,
      });
      setGrants((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch {
      setError("撤回未完成，请刷新后重试。");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className={cn("sm:max-w-md", seniorMode && "p-5")} showCloseButton={!seniorMode}>
        <DialogHeader>
          <DialogTitle className={cn(seniorMode && "text-2xl")}>医生复核授权</DialogTitle>
          <DialogDescription className={textClass}>仅允许医生查看并复核五大处方草案。</DialogDescription>
        </DialogHeader>
        <form className="mt-3 grid gap-3" onSubmit={submit}>
          <div className="grid gap-2">
            <Label htmlFor="doctor-review-code" className={cn(seniorMode && "text-lg")}>医生复核代码</Label>
            <Input
              id="doctor-review-code"
              value={doctorActorId}
              onChange={(event) => setDoctorActorId(event.target.value.trim())}
              placeholder="usr_account_…"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              maxLength={44}
              className={cn("font-mono", seniorMode && "h-12 text-base")}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="review-expiry" className={cn(seniorMode && "text-lg")}>授权期限</Label>
            <select
              id="review-expiry"
              value={expiryDays}
              onChange={(event) => setExpiryDays(Number(event.target.value))}
              className={cn("h-10 rounded-md border border-input bg-background px-3", seniorMode && "h-12 text-lg")}
            >
              <option value={30}>30 天</option>
              <option value={90}>90 天</option>
              <option value={365}>1 年</option>
            </select>
          </div>
          {error && <p role="alert" className={cn("rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive", textClass)}>{error}</p>}
          <DialogFooter className={cn("gap-2", seniorMode && "flex-row justify-end gap-3")}>
            <Button type="submit" disabled={pending || !doctorActorIdPattern.test(doctorActorId)} className={cn(seniorMode && "min-h-12 text-lg")}>
              {pending ? "正在保存…" : "授权复核"}
            </Button>
          </DialogFooter>
        </form>
        <div className="border-t pt-4">
          <h3 className={cn("font-medium", seniorMode && "text-lg")}>当前授权</h3>
          {loading ? <InlineLoadingState className="min-h-20" message="正在读取授权" /> : grants.length === 0 ? (
            <p className={cn("mt-2 text-muted-foreground", textClass)}>暂无医生复核授权</p>
          ) : (
            <ul className="mt-2 grid gap-2">
              {grants.map((grant) => (
                <li key={grant.id} className={cn("flex items-center justify-between gap-3 rounded-lg border p-3", textClass)}>
                  <div className="min-w-0">
                    <p className="truncate font-mono text-xs">{grant.doctor_actor_id}</p>
                    <p className="text-muted-foreground">{grant.status === "active" ? `至 ${displayExpiry(grant.expires_at)}` : grant.status === "revoked" ? "已撤回" : "已到期"}</p>
                  </div>
                  {grant.status === "active" && <Button type="button" variant="outline" size="sm" disabled={pending} onClick={() => void revoke(grant)} className={cn(seniorMode && "min-h-11 text-base")}>撤回</Button>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
