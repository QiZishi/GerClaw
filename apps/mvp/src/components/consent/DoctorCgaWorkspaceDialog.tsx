"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { InlineLoadingState } from "@/components/ui/inline-loading-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { listAuthorizedCgaReports } from "@/services/gerclaw/doctor-cga-reports";
import type { CgaHistoryItem } from "@/services/gerclaw/schemas";

const accountIdPattern = /^usr_account_[a-f0-9]{32}$/;
const scaleNames = { phq9: "PHQ-9", sas: "SAS", psqi: "PSQI", minicog: "Mini-Cog", mmse: "MMSE" } as const;
const severityNames = {
  none: "无",
  minimal: "轻微",
  mild: "轻度",
  moderate: "中度",
  moderately_severe: "中重度",
  severe: "重度",
  good: "良好",
  fair: "一般",
  average: "中等",
  poor: "较差",
  screen_negative: "筛查阴性",
  possible_impairment: "可能存在认知问题",
  normal: "正常范围",
  mild_impairment: "轻度受损",
  moderate_impairment: "中度受损",
  severe_impairment: "重度受损",
} as const;

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function reportSummary(item: CgaHistoryItem): string {
  const { report } = item;
  const standardScore = report.standard_score === null ? "" : `；标准分 ${report.standard_score}`;
  return `总分 ${report.total_score}/${report.score_max}${standardScore}；筛查分级 ${severityNames[report.severity]}`;
}

export function DoctorCgaWorkspaceDialog({
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
  const [items, setItems] = useState<CgaHistoryItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textClass = seniorMode ? "text-lg leading-8" : "text-sm leading-6";

  function close(nextOpen: boolean) {
    if (!nextOpen) {
      setPatientActorId("");
      setItems(null);
      setError(null);
    }
    onOpenChange(nextOpen);
  }

  async function load() {
    if (loading || !accountIdPattern.test(patientActorId.trim())) return;
    setLoading(true);
    setError(null);
    try {
      setItems((await listAuthorizedCgaReports(patientActorId)).items);
    } catch {
      setItems(null);
      setError("未找到可查看的 CGA 报告，或患者尚未授权。");
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
        const history = await listAuthorizedCgaReports(initialPatientActorId);
        if (active) setItems(history.items);
      } catch {
        if (active) {
          setItems(null);
          setError("未找到可查看的 CGA 报告，或患者尚未授权。");
        }
      } finally {
        if (active) setLoading(false);
      }
    });
    return () => { active = false; };
  }, [initialPatientActorId, open]);

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className={cn("max-h-[90vh] overflow-y-auto sm:max-w-3xl", seniorMode && "p-5")} showCloseButton={!seniorMode}>
        <DialogHeader>
          <DialogTitle className={cn(seniorMode && "text-2xl")}>CGA 报告工作区</DialogTitle>
          <DialogDescription className={textClass}>输入患者代码后查看已授权的完成筛查摘要。</DialogDescription>
        </DialogHeader>
        <div className="mt-3 flex gap-2">
          <div className="min-w-0 flex-1">
            <Label htmlFor="cga-patient-code" className="sr-only">患者代码</Label>
            <Input
              id="cga-patient-code"
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
            查看报告
          </Button>
        </div>
        {error && <p role="alert" className={cn("rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive", textClass)}>{error}</p>}
        {loading && <InlineLoadingState message="正在读取 CGA 报告" className="min-h-24" />}
        {items && !loading && (items.length === 0 ? (
          <p className={cn("py-5 text-center text-muted-foreground", textClass)}>暂无已完成的筛查报告</p>
        ) : (
          <div className="grid gap-3">
            {items.map((item) => (
              <article key={item.assessment_id} className="rounded-xl border p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className={cn("font-semibold", seniorMode && "text-xl")}>{scaleNames[item.scale_id]} 筛查</h3>
                  <time className="text-xs text-muted-foreground">{formatDate(item.completed_at)}</time>
                </div>
                <p className={cn("mt-2", textClass)}>{reportSummary(item)}</p>
                {item.report.safety_messages.map((message) => (
                  <p key={message} className={cn("mt-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive", textClass)}>{message}</p>
                ))}
                <p className={cn("mt-3 text-muted-foreground", textClass)}>{item.report.disclaimer}</p>
              </article>
            ))}
          </div>
        ))}
      </DialogContent>
    </Dialog>
  );
}
