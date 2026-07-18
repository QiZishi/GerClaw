"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InlineLoadingState } from "@/components/ui/inline-loading-state";
import { cn } from "@/lib/utils";
import { listAuthorizedMedicationReviewDrafts } from "@/services/gerclaw/doctor-medication-review";
import type { DoctorMedicationReviewDraftList, MedicationReviewDraft } from "@/services/gerclaw/schemas";

const accountIdPattern = /^usr_account_[a-f0-9]{32}$/;

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function severityLabel(severity: MedicationReviewDraft["findings"][number]["severity"]): string {
  return { contraindicated: "禁忌", major: "重要", moderate: "中等", minor: "轻度" }[severity];
}

export function DoctorMedicationReviewDialog({
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
  const [result, setResult] = useState<DoctorMedicationReviewDraftList | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textClass = seniorMode ? "text-lg leading-8" : "text-sm leading-6";

  function close(nextOpen: boolean) {
    if (!nextOpen) {
      setPatientActorId("");
      setResult(null);
      setError(null);
    }
    onOpenChange(nextOpen);
  }

  async function fetchDrafts(patientId: string) {
    setLoading(true);
    setError(null);
    try {
      setResult(await listAuthorizedMedicationReviewDrafts(patientId));
    } catch {
      setResult(null);
      setError("未找到用药审查记录，或患者尚未授权。");
    } finally {
      setLoading(false);
    }
  }

  async function load() {
    const patientId = patientActorId.trim();
    if (loading || !accountIdPattern.test(patientId)) return;
    await fetchDrafts(patientId);
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
        const drafts = await listAuthorizedMedicationReviewDrafts(initialPatientActorId);
        if (active) setResult(drafts);
      } catch {
        if (active) {
          setResult(null);
          setError("未找到用药审查记录，或患者尚未授权。");
        }
      } finally {
        if (active) setLoading(false);
      }
    });
    return () => { active = false; };
  }, [initialPatientActorId, open]);

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className={cn("max-h-[90vh] overflow-y-auto sm:max-w-4xl", seniorMode && "p-5")} showCloseButton={!seniorMode}>
        <DialogHeader>
          <DialogTitle className={cn(seniorMode && "text-2xl")}>用药审查记录</DialogTitle>
          <DialogDescription className={textClass}>输入患者代码后查看患者授权的来源绑定审查结论。</DialogDescription>
        </DialogHeader>
        <div className="mt-3 flex gap-2">
          <div className="min-w-0 flex-1">
            <Label htmlFor="medication-review-patient-code" className="sr-only">患者代码</Label>
            <Input id="medication-review-patient-code" value={patientActorId} onChange={(event) => setPatientActorId(event.target.value.trim())} placeholder="患者代码" autoCapitalize="none" autoCorrect="off" spellCheck={false} maxLength={44} className={cn("font-mono", seniorMode && "h-12 text-base")} />
          </div>
          <Button type="button" disabled={loading || !accountIdPattern.test(patientActorId)} onClick={() => void load()} className={cn(seniorMode && "min-h-12 text-lg")}>查看记录</Button>
        </div>
        {error && <p role="alert" className={cn("rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive", textClass)}>{error}</p>}
        {loading && <InlineLoadingState message="正在读取用药审查" className="min-h-24" />}
        {result && !loading && (result.items.length === 0 ? (
          <p className={cn("py-5 text-center text-muted-foreground", textClass)}>暂无已保存的用药审查记录</p>
        ) : (
          <div className="grid gap-4">
            {result.items.map((record) => (
              <article key={record.draft_id} className="rounded-xl border p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className={cn("font-semibold", seniorMode && "text-xl")}>规则审查 · 输入版本 {record.intake_revision}</h3>
                  <time className="text-xs text-muted-foreground">{formatDate(record.created_at)}</time>
                </div>
                <p className={cn("mt-2 text-muted-foreground", textClass)}>{record.draft.conclusion}</p>
                <div className="mt-3 grid gap-2">
                  {record.draft.findings.length === 0 ? <p className={textClass}>未命中已安装规则；有限规则未命中不代表无风险。</p> : record.draft.findings.map((finding) => (
                    <section key={finding.finding_id} className={cn("rounded-lg bg-muted/50 p-3", textClass)}>
                      <p className="font-medium">{severityLabel(finding.severity)} · {finding.title}</p>
                      <p className="mt-1">{finding.conclusion}</p>
                      <p className="mt-1 text-muted-foreground">建议：{finding.clinician_action}</p>
                      <p className="mt-1 text-muted-foreground">来源：{finding.source_ids.join("、") || "未绑定"}</p>
                    </section>
                  ))}
                </div>
                <details className={cn("mt-3", textClass)}>
                  <summary className="cursor-pointer font-medium">查看规则来源</summary>
                  <ul className="mt-2 grid gap-2 text-muted-foreground">
                    {record.draft.sources.map((source) => <li key={source.source_id}>{source.source_id} · {source.title}（{source.publisher}，{source.locator}）</li>)}
                  </ul>
                </details>
              </article>
            ))}
          </div>
        ))}
      </DialogContent>
    </Dialog>
  );
}
