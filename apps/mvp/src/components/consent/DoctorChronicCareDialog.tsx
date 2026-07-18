"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InlineLoadingState } from "@/components/ui/inline-loading-state";
import { cn } from "@/lib/utils";
import {
  getAuthorizedChronicCareCondition,
  listAuthorizedChronicCareConditions,
} from "@/services/gerclaw/doctor-chronic-care";
import type { DoctorChronicCareConditionDetail, DoctorChronicCareConditionList } from "@/services/gerclaw/schemas";

const accountIdPattern = /^usr_account_[a-f0-9]{32}$/;
const directionLabel = {
  rising: "比上次高",
  falling: "比上次低",
  unchanged: "与上次相同",
  insufficient_data: "记录不足，暂不比较",
} as const;

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function DoctorChronicCareDialog({
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
  const [conditions, setConditions] = useState<DoctorChronicCareConditionList | null>(null);
  const [detail, setDetail] = useState<DoctorChronicCareConditionDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textClass = seniorMode ? "text-lg leading-8" : "text-sm leading-6";

  function close(nextOpen: boolean) {
    if (!nextOpen) {
      setPatientActorId("");
      setConditions(null);
      setDetail(null);
      setError(null);
    }
    onOpenChange(nextOpen);
  }

  async function loadConditions(patientId: string) {
    setLoading(true);
    setError(null);
    setDetail(null);
    try {
      setConditions(await listAuthorizedChronicCareConditions(patientId));
    } catch {
      setConditions(null);
      setError("未找到慢病记录，或患者尚未授权。");
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(conditionId: string) {
    if (!accountIdPattern.test(patientActorId) || detailLoading) return;
    setDetailLoading(true);
    setError(null);
    try {
      setDetail(await getAuthorizedChronicCareCondition({ patientActorId, conditionId }));
    } catch {
      setDetail(null);
      setError("记录读取失败，授权可能已撤回。");
    } finally {
      setDetailLoading(false);
    }
  }

  useEffect(() => {
    if (!open || !initialPatientActorId || !accountIdPattern.test(initialPatientActorId)) return;
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      setPatientActorId(initialPatientActorId);
      await loadConditions(initialPatientActorId);
    });
    return () => { active = false; };
  }, [initialPatientActorId, open]);

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className={cn("max-h-[90vh] overflow-y-auto sm:max-w-4xl", seniorMode && "p-5")} showCloseButton={!seniorMode}>
        <DialogHeader>
          <DialogTitle className={cn(seniorMode && "text-2xl")}>患者慢病记录</DialogTitle>
          <DialogDescription className={textClass}>仅显示患者主动授权的自述记录和数值变化。</DialogDescription>
        </DialogHeader>
        <div className="mt-3 flex gap-2">
          <div className="min-w-0 flex-1">
            <Label htmlFor="doctor-chronic-patient-code" className="sr-only">患者代码</Label>
            <Input id="doctor-chronic-patient-code" value={patientActorId} onChange={(event) => setPatientActorId(event.target.value.trim())} placeholder="患者代码" autoCapitalize="none" autoCorrect="off" spellCheck={false} maxLength={44} className={cn("font-mono", seniorMode && "h-12 text-base")} />
          </div>
          <Button type="button" disabled={loading || !accountIdPattern.test(patientActorId)} onClick={() => void loadConditions(patientActorId)} className={cn(seniorMode && "min-h-12 text-lg")}>查看记录</Button>
        </div>
        {error && <p role="alert" className={cn("rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive", textClass)}>{error}</p>}
        {loading && <InlineLoadingState message="正在读取慢病记录" className="min-h-24" />}
        {conditions && !loading && (conditions.items.length === 0 ? (
          <p className={cn("py-5 text-center text-muted-foreground", textClass)}>暂无已保存的慢病记录</p>
        ) : (
          <div className="grid gap-3">
            <h3 className={cn("font-medium", seniorMode && "text-xl")}>自述健康情况</h3>
            {conditions.items.map((condition) => (
              <div key={condition.condition_id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3">
                <div><p className={cn("font-medium", textClass)}>{condition.label}</p><p className={cn("text-muted-foreground", textClass)}>患者自述 · {formatDate(condition.updated_at)}</p></div>
                <Button type="button" variant="outline" disabled={detailLoading} onClick={() => void loadDetail(condition.condition_id)} className={cn(seniorMode && "min-h-12 text-lg")}>查看测量</Button>
              </div>
            ))}
          </div>
        ))}
        {detailLoading && <InlineLoadingState message="正在读取测量记录" className="min-h-20" />}
        {detail && !detailLoading && <section className="mt-2 grid gap-4 rounded-xl border p-4" aria-labelledby="doctor-chronic-detail-title">
          <div><h3 id="doctor-chronic-detail-title" className={cn("font-semibold", seniorMode && "text-xl")}>{detail.condition.label}</h3><p className={cn("mt-1 text-muted-foreground", textClass)}>以下仅为患者记录的数值和算术比较，不代表诊断、目标或治疗建议。</p></div>
          <div className="grid gap-2"><h4 className={cn("font-medium", textClass)}>数值变化</h4>{detail.trends.length === 0 ? <p className={cn("text-muted-foreground", textClass)}>暂无可比较的记录</p> : detail.trends.map((trend) => <p key={`${trend.metric_label}-${trend.unit}`} className={cn("rounded-lg bg-muted/50 p-3", textClass)}>{trend.metric_label}：{trend.latest_value} {trend.unit} · {directionLabel[trend.direction]}</p>)}</div>
          <div className="grid gap-2"><h4 className={cn("font-medium", textClass)}>最近测量</h4>{detail.measurements.length === 0 ? <p className={cn("text-muted-foreground", textClass)}>暂无测量记录</p> : <ul className={cn("grid gap-2", textClass)}>{detail.measurements.map((measurement) => <li key={measurement.measurement_id} className="rounded-lg bg-muted/50 p-3">{measurement.metric_label}：{measurement.value} {measurement.unit} · {formatDate(measurement.measured_at)}</li>)}</ul>}</div>
        </section>}
      </DialogContent>
    </Dialog>
  );
}
