"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InlineLoadingState } from "@/components/ui/inline-loading-state";
import { cn } from "@/lib/utils";
import { fivePrescriptionDraftToMarkdown } from "@/services/gerclaw/prescription-report";
import { listAuthorizedPrescriptionDrafts, submitPrescriptionDraftReview } from "@/services/gerclaw/doctor-prescription-review";
import type { DoctorPrescriptionDraftList } from "@/services/gerclaw/schemas";

const accountIdPattern = /^usr_account_[a-f0-9]{32}$/;

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function DoctorPrescriptionReviewDialog({
  open,
  onOpenChange,
  seniorMode,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  seniorMode: boolean;
}) {
  const [patientActorId, setPatientActorId] = useState("");
  const [result, setResult] = useState<DoctorPrescriptionDraftList | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [pendingDraftId, setPendingDraftId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const textClass = seniorMode ? "text-lg leading-8" : "text-sm leading-6";

  function close(nextOpen: boolean) {
    if (!nextOpen) {
      setPatientActorId("");
      setResult(null);
      setNotes({});
      setError(null);
    }
    onOpenChange(nextOpen);
  }

  async function load() {
    if (loading || !accountIdPattern.test(patientActorId.trim())) return;
    setLoading(true);
    setError(null);
    try {
      setResult(await listAuthorizedPrescriptionDrafts(patientActorId));
    } catch {
      setResult(null);
      setError("未找到可复核的草案，或患者尚未授权。");
    } finally {
      setLoading(false);
    }
  }

  async function submit(draftId: string, decision: "approved" | "returned") {
    const reviewNote = notes[draftId]?.trim() ?? "";
    if (!result || !reviewNote || pendingDraftId) return;
    setPendingDraftId(draftId);
    setError(null);
    try {
      const review = await submitPrescriptionDraftReview({
        patientActorId,
        draftId,
        decision,
        reviewNote,
      });
      setResult((current) => current && {
        items: current.items.map((draft) => draft.draft_id === draftId
          ? { ...draft, reviews: [review, ...draft.reviews] }
          : draft),
      });
      setNotes((current) => ({ ...current, [draftId]: "" }));
    } catch {
      setError("复核意见未保存，请稍后重试。");
    } finally {
      setPendingDraftId(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className={cn("max-h-[90vh] overflow-y-auto sm:max-w-4xl", seniorMode && "p-5")} showCloseButton={!seniorMode}>
        <DialogHeader>
          <DialogTitle className={cn(seniorMode && "text-2xl")}>五大处方草案复核</DialogTitle>
          <DialogDescription className={textClass}>输入患者代码后查看已授权的草案。</DialogDescription>
        </DialogHeader>
        <div className="mt-3 flex gap-2">
          <div className="min-w-0 flex-1">
            <Label htmlFor="review-patient-code" className="sr-only">患者代码</Label>
            <Input
              id="review-patient-code"
              value={patientActorId}
              onChange={(event) => setPatientActorId(event.target.value.trim())}
              placeholder="患者代码"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              maxLength={44}
              className={cn("font-mono", seniorMode && "h-12 text-base")}
            />
          </div>
          <Button type="button" disabled={loading || !accountIdPattern.test(patientActorId)} onClick={() => void load()} className={cn(seniorMode && "min-h-12 text-lg")}>
            查看草案
          </Button>
        </div>
        {error && <p role="alert" className={cn("rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive", textClass)}>{error}</p>}
        {loading && <InlineLoadingState message="正在读取草案" className="min-h-24" />}
        {result && !loading && (result.items.length === 0 ? (
          <p className={cn("py-5 text-center text-muted-foreground", textClass)}>暂无可复核的草案</p>
        ) : (
          <div className="grid gap-4">
            {result.items.map((draft) => (
              <article key={draft.draft_id} className="rounded-xl border p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className={cn("font-semibold", seniorMode && "text-xl")}>待临床复核草案</h3>
                  <time className="text-xs text-muted-foreground">{formatDate(draft.created_at)}</time>
                </div>
                <details className={cn("mt-3", textClass)}>
                  <summary className="cursor-pointer font-medium">查看草案内容</summary>
                  <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-muted/50 p-3 font-sans text-sm leading-6">{fivePrescriptionDraftToMarkdown(draft.draft)}</pre>
                </details>
                {draft.reviews.length > 0 && <div className={cn("mt-3 rounded-lg bg-muted/50 p-3", textClass)}>
                  <p className="font-medium">我的最近意见</p>
                  <p className="mt-1">{draft.reviews[0].decision === "approved" ? "已通过" : "已退回"}：{draft.reviews[0].review_note}</p>
                </div>}
                <div className="mt-3 grid gap-2">
                  <Label htmlFor={`review-note-${draft.draft_id}`} className={cn(seniorMode && "text-lg")}>复核意见</Label>
                  <textarea
                    id={`review-note-${draft.draft_id}`}
                    value={notes[draft.draft_id] ?? ""}
                    onChange={(event) => setNotes((current) => ({ ...current, [draft.draft_id]: event.target.value.slice(0, 5_000) }))}
                    maxLength={5_000}
                    className={cn("min-h-24 rounded-md border border-input bg-background p-3", seniorMode && "min-h-32 text-lg")}
                  />
                  <DialogFooter className={cn("gap-2", seniorMode && "flex-row justify-end gap-3")}>
                    <Button type="button" variant="outline" disabled={!notes[draft.draft_id]?.trim() || pendingDraftId !== null} onClick={() => void submit(draft.draft_id, "returned")} className={cn(seniorMode && "min-h-12 text-lg")}>退回补充</Button>
                    <Button type="button" disabled={!notes[draft.draft_id]?.trim() || pendingDraftId !== null} onClick={() => void submit(draft.draft_id, "approved")} className={cn(seniorMode && "min-h-12 text-lg")}>{pendingDraftId === draft.draft_id ? "正在保存…" : "记录通过"}</Button>
                  </DialogFooter>
                </div>
              </article>
            ))}
          </div>
        ))}
      </DialogContent>
    </Dialog>
  );
}
