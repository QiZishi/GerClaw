"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { InlineLoadingState } from "@/components/ui/inline-loading-state";
import { cn } from "@/lib/utils";
import { toast } from "@/components/ui/toast";
import { acknowledgeRiskAlert, listRiskAlerts } from "@/services/gerclaw/risk-alerts";
import type { RiskAlert } from "@/services/gerclaw/schemas";

interface RiskAlertLedgerProps {
  seniorMode: boolean;
}

function idempotencyKey(): string {
  return `idem_${crypto.randomUUID().replaceAll("-", "")}`;
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

/** Displays only server-determined, owner-scoped alerts. It never scores or dismisses risk in the browser. */
export function RiskAlertLedger({ seniorMode }: RiskAlertLedgerProps) {
  const [alerts, setAlerts] = useState<RiskAlert[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [acknowledgingId, setAcknowledgingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState("loading");
    try {
      const result = await listRiskAlerts();
      setAlerts(result.items);
      setState("ready");
    } catch (error) {
      setState("error");
      toast.show(error instanceof Error ? error.message : "安全提醒暂时无法读取，请稍后重试");
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const acknowledge = async (alert: RiskAlert) => {
    if (acknowledgingId) return;
    setAcknowledgingId(alert.alert_id);
    try {
      const updated = await acknowledgeRiskAlert(alert, idempotencyKey());
      setAlerts((previous) => previous.map((item) => item.alert_id === updated.alert_id ? updated : item));
      toast.show("已记录您已了解此提醒；如有紧急情况，请仍按提示立即求助。");
    } catch (error) {
      toast.show(error instanceof Error ? error.message : "暂时无法记录，请刷新后重试");
    } finally {
      setAcknowledgingId(null);
    }
  };

  const active = alerts.filter((alert) => alert.status === "active");
  const acknowledged = alerts.filter((alert) => alert.status === "acknowledged");
  const headingClass = seniorMode ? "text-2xl" : "text-xl";
  const bodyClass = seniorMode ? "text-lg leading-8" : "text-sm leading-6";

  return (
    <section className={cn("mx-auto w-full max-w-4xl space-y-5 px-4 py-5 sm:px-6", seniorMode && "max-w-5xl py-6")} aria-labelledby="risk-alert-title">
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-red-700 dark:text-red-400">
          <AlertTriangle className={cn("size-5", seniorMode && "size-6")} aria-hidden="true" />
          <h1 id="risk-alert-title" className={cn("font-semibold", headingClass)}>我的安全提醒</h1>
        </div>
        <p className={cn("text-muted-foreground", bodyClass)}>这里只显示系统已确定的本人提醒。“我已了解”不会解除风险、不会取消就医建议，也不会自动联系任何人。</p>
      </div>

      {state === "loading" && <InlineLoadingState message="正在读取安全提醒" className={cn("min-h-28", seniorMode && "text-lg")} />}
      {state === "error" && <Card className="border-destructive/40"><CardContent className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between"><p className={cn("text-destructive", seniorMode && "text-lg")}>安全提醒暂时无法读取，请检查网络后重试。</p><Button type="button" variant="outline" onClick={() => void load()} className={cn("min-h-11", seniorMode && "min-h-12 text-lg")}>重新读取</Button></CardContent></Card>}
      {state === "ready" && active.length === 0 && <Card className="border-dashed"><CardContent className={cn("py-8 text-center text-muted-foreground", seniorMode && "py-10 text-lg")}>当前没有需要您查看的安全提醒。</CardContent></Card>}
      {state === "ready" && active.map((alert) => <Card key={alert.alert_id} className="border-2 border-red-500 bg-red-50/70 dark:bg-red-950/20"><CardHeader><CardTitle className={cn("flex items-center gap-2 text-red-900 dark:text-red-100", seniorMode && "text-xl")}><AlertTriangle className="size-5" aria-hidden="true" />{alert.title}</CardTitle><CardDescription className={cn("text-red-900/80 dark:text-red-100/80", bodyClass)}>{alert.message}</CardDescription></CardHeader><CardContent className="space-y-4"><p className={cn("font-medium text-red-950 dark:text-red-50", bodyClass)}>{alert.action}</p><p className={cn("text-muted-foreground", seniorMode ? "text-base" : "text-xs")}>创建于 {formatDateTime(alert.created_at)}</p><Button type="button" variant="outline" onClick={() => void acknowledge(alert)} disabled={acknowledgingId !== null} className={cn("min-h-11 border-red-400 text-red-900 hover:bg-red-100 dark:text-red-100", seniorMode && "min-h-12 px-5 text-lg")}>{acknowledgingId === alert.alert_id ? "正在记录" : "我已了解此提醒"}</Button></CardContent></Card>)}
      {state === "ready" && acknowledged.length > 0 && <Card><CardHeader><CardTitle className={cn("flex items-center gap-2", seniorMode && "text-xl")}><CheckCircle2 className="size-5 text-muted-foreground" aria-hidden="true" />已了解的提醒</CardTitle><CardDescription className={cn(bodyClass)}>保留记录；“已了解”不代表风险已解除。</CardDescription></CardHeader><CardContent><ul className="divide-y rounded-lg border">{acknowledged.map((alert) => <li key={alert.alert_id} className={cn("px-3 py-3", bodyClass)}><p className="font-medium">{alert.title}</p><p className="mt-1 text-muted-foreground">{alert.acknowledged_at ? `已于 ${formatDateTime(alert.acknowledged_at)} 记录了解` : "已记录了解"}</p></li>)}</ul></CardContent></Card>}
    </section>
  );
}
