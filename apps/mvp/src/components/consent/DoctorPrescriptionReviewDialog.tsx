"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InlineLoadingState } from "@/components/ui/inline-loading-state";
import { MarkdownEditor } from "@/components/editor/MarkdownEditor";
import { cn } from "@/lib/utils";
import { fivePrescriptionDraftToMarkdown } from "@/services/gerclaw/prescription-report";
import { listAuthorizedPrescriptionDrafts, submitPrescriptionDraftReview } from "@/services/gerclaw/doctor-prescription-review";
import type { DoctorPrescriptionDraftList, FivePrescriptionDraft } from "@/services/gerclaw/schemas";

const accountIdPattern = /^usr_account_[a-f0-9]{32}$/;

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function DoctorPrescriptionReviewDialog({
  open,
  onOpenChange,
  seniorMode,
  initialPatientActorId = null,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  seniorMode: boolean;
  initialPatientActorId?: string | null;
}) {
  const [patientActorId, setPatientActorId] = useState("");
  const [result, setResult] = useState<DoctorPrescriptionDraftList | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [editingDraftId, setEditingDraftId] = useState<string | null>(null);
  const [amendments, setAmendments] = useState<Record<string, string>>({});
  const [amendmentEvidenceIds, setAmendmentEvidenceIds] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(false);
  const [pendingDraftId, setPendingDraftId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const textClass = seniorMode ? "text-lg leading-8" : "text-sm leading-6";

  function close(nextOpen: boolean) {
    if (!nextOpen) {
      setPatientActorId("");
      setResult(null);
      setNotes({});
      setEditingDraftId(null);
      setAmendments({});
      setAmendmentEvidenceIds({});
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

  useEffect(() => {
    if (!open || !initialPatientActorId || !accountIdPattern.test(initialPatientActorId)) return;
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      setPatientActorId(initialPatientActorId);
      setLoading(true);
      setError(null);
      try {
        const drafts = await listAuthorizedPrescriptionDrafts(initialPatientActorId);
        if (active) setResult(drafts);
      } catch {
        if (active) {
          setResult(null);
          setError("未找到可复核的草案，或患者尚未授权。");
        }
      } finally {
        if (active) setLoading(false);
      }
    });
    return () => { active = false; };
  }, [initialPatientActorId, open]);

  function beginEditing(draftId: string, draft: FivePrescriptionDraft) {
    setEditingDraftId(draftId);
    setAmendments((current) => ({ ...current, [draftId]: current[draftId] ?? fivePrescriptionDraftToMarkdown(draft) }));
    setAmendmentEvidenceIds((current) => ({
      ...current,
      [draftId]: current[draftId] ?? draft.evidence_sources.map((source) => source.evidence_id),
    }));
  }

  function toggleEvidence(draftId: string, evidenceId: string) {
    setAmendmentEvidenceIds((current) => {
      const selected = new Set(current[draftId] ?? []);
      if (selected.has(evidenceId)) selected.delete(evidenceId);
      else selected.add(evidenceId);
      return { ...current, [draftId]: [...selected] };
    });
  }

  async function submit(draftId: string, decision: "approved" | "returned") {
    const reviewNote = notes[draftId]?.trim() ?? "";
    if (!result || !reviewNote || pendingDraftId) return;
    const isEditing = editingDraftId === draftId;
    const amendedMarkdown = isEditing ? amendments[draftId]?.trim() : undefined;
    const evidenceIds = isEditing ? amendmentEvidenceIds[draftId] ?? [] : [];
    if (isEditing && (!amendedMarkdown || evidenceIds.length === 0)) {
      setError("请保留修订内容并选择至少一条依据。");
      return;
    }
    setPendingDraftId(draftId);
    setError(null);
    try {
      const review = await submitPrescriptionDraftReview({
        patientActorId,
        draftId,
        decision,
        reviewNote,
        amendedMarkdown,
        amendmentEvidenceIds: evidenceIds,
      });
      setResult((current) => current && {
        items: current.items.map((draft) => draft.draft_id === draftId
          ? { ...draft, reviews: [review, ...draft.reviews] }
          : draft),
      });
      setNotes((current) => ({ ...current, [draftId]: "" }));
      setEditingDraftId((current) => current === draftId ? null : current);
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
                  {draft.reviews[0].amended_markdown && <p className="mt-1 text-muted-foreground">已保存医生修订内容（依据 {draft.reviews[0].amendment_evidence_ids.join("、")}）。</p>}
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
                  {editingDraftId === draft.draft_id ? <div className="grid gap-3 rounded-lg border p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className={cn("font-medium", textClass)}>医生修订内容</p>
                      <Button type="button" variant="ghost" onClick={() => setEditingDraftId(null)}>取消编辑</Button>
                    </div>
                    <p className={cn("text-muted-foreground", textClass)}>修订版保留原草案和所选依据，可实时预览。</p>
                    <MarkdownEditor
                      value={amendments[draft.draft_id] ?? ""}
                      onChange={(value) => setAmendments((current) => ({ ...current, [draft.draft_id]: value.slice(0, 50_000) }))}
                      className="max-h-[60vh] rounded-lg border"
                    />
                    <fieldset className="grid gap-2">
                      <legend className={cn("font-medium", textClass)}>修订依据</legend>
                      {draft.draft.evidence_sources.map((source) => {
                        const selected = (amendmentEvidenceIds[draft.draft_id] ?? []).includes(source.evidence_id);
                        return <label key={source.evidence_id} className={cn("flex items-start gap-2 rounded-md border p-2", textClass)}>
                          <input type="checkbox" checked={selected} onChange={() => toggleEvidence(draft.draft_id, source.evidence_id)} className="mt-1 size-4" />
                          <span><span className="font-mono">{source.evidence_id}</span> · {source.title}</span>
                        </label>;
                      })}
                    </fieldset>
                  </div> : <Button type="button" variant="outline" onClick={() => beginEditing(draft.draft_id, draft.draft)} className={cn("w-fit", seniorMode && "min-h-12 text-lg")}>编辑医生修订版</Button>}
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
