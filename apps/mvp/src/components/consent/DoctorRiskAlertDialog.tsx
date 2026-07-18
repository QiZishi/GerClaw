"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InlineLoadingState } from "@/components/ui/inline-loading-state";
import { cn } from "@/lib/utils";
import { listAuthorizedRiskAlerts } from "@/services/gerclaw/doctor-risk-alerts";
import type { RiskAlert } from "@/services/gerclaw/schemas";

const patientIdPattern = /^usr_account_[a-f0-9]{32}$/;
const severity = { critical: "紧急", high: "高风险" } as const;

export function DoctorRiskAlertDialog({ open, onOpenChange, seniorMode, initialPatientActorId = null }: { open: boolean; onOpenChange: (open: boolean) => void; seniorMode: boolean; initialPatientActorId?: string | null }) {
  const [patientActorId, setPatientActorId] = useState("");
  const [alerts, setAlerts] = useState<RiskAlert[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textClass = seniorMode ? "text-lg leading-8" : "text-sm leading-6";
  async function load(value = patientActorId) { if (!patientIdPattern.test(value) || loading) return; setLoading(true); setError(null); try { setAlerts((await listAuthorizedRiskAlerts(value)).items); } catch { setAlerts(null); setError("未找到安全提醒，或患者尚未授权。"); } finally { setLoading(false); } }
  useEffect(() => {
    if (!open || !initialPatientActorId || !patientIdPattern.test(initialPatientActorId)) return;
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      setPatientActorId(initialPatientActorId);
      setLoading(true);
      setError(null);
      try {
        const result = await listAuthorizedRiskAlerts(initialPatientActorId);
        if (active) setAlerts(result.items);
      } catch {
        if (active) {
          setAlerts(null);
          setError("未找到安全提醒，或患者尚未授权。");
        }
      } finally {
        if (active) setLoading(false);
      }
    });
    return () => { active = false; };
  }, [open, initialPatientActorId]);
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className={cn("max-h-[90vh] overflow-y-auto sm:max-w-3xl", seniorMode && "p-5")}><DialogHeader><DialogTitle className={cn(seniorMode && "text-2xl")}>患者安全提醒</DialogTitle><DialogDescription className={textClass}>仅查看患者明确授权的当前提醒；不包含原始对话、附件或检查答案。</DialogDescription></DialogHeader><div className="flex gap-2"><div className="min-w-0 flex-1"><Label htmlFor="risk-alert-patient-code" className="sr-only">患者代码</Label><Input id="risk-alert-patient-code" value={patientActorId} onChange={(event) => setPatientActorId(event.target.value.trim())} placeholder="患者代码" className={cn("font-mono", seniorMode && "h-12 text-base")} /></div><Button type="button" onClick={() => void load()} disabled={loading || !patientIdPattern.test(patientActorId)} className={cn(seniorMode && "min-h-12 text-lg")}>查看提醒</Button></div>{loading && <InlineLoadingState message="正在读取安全提醒" className="min-h-24" />}{error && <p role="alert" className={cn("rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive", textClass)}>{error}</p>}{alerts && !loading && (alerts.length ? <div className="grid gap-3">{alerts.map((alert) => <article key={alert.alert_id} className={cn("rounded-xl border p-4", alert.severity === "critical" && "border-destructive/50")}><p className="font-semibold">{severity[alert.severity]} · {alert.title}</p><p className={cn("mt-2", textClass)}>{alert.message}</p><p className={cn("mt-2 text-muted-foreground", textClass)}>{alert.action}</p></article>)}</div> : <p className={cn("py-5 text-center text-muted-foreground", textClass)}>暂无当前安全提醒</p>)}</DialogContent></Dialog>;
}
