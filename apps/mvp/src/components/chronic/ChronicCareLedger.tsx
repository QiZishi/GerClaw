"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, BarChart3, ClipboardPlus, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { InlineLoadingState } from "@/components/ui/inline-loading-state";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { toast } from "@/components/ui/toast";
import {
  addChronicMeasurement,
  createChronicCondition,
  listChronicConditions,
  listChronicMeasurements,
  listChronicTrends,
} from "@/services/gerclaw/chronic-care";
import type { ChronicCondition, ChronicMeasurement, ChronicTrend } from "@/services/gerclaw/schemas";

const directionLabel: Record<ChronicTrend["direction"], string> = {
  rising: "比上次高",
  falling: "比上次低",
  unchanged: "与上次相同",
  insufficient_data: "还需要至少两次记录",
};

function localDateTimeNow(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 16);
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatValue(value: number): string {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 3 }).format(value);
}

interface ChronicCareLedgerProps {
  seniorMode: boolean;
}

/**
 * A personal, append-only measurement notebook. It intentionally makes no
 * medical judgement: the server compares only identical metric labels.
 */
export function ChronicCareLedger({ seniorMode }: ChronicCareLedgerProps) {
  const [conditions, setConditions] = useState<ChronicCondition[]>([]);
  const [selectedConditionId, setSelectedConditionId] = useState<string | null>(null);
  const [measurements, setMeasurements] = useState<ChronicMeasurement[]>([]);
  const [trends, setTrends] = useState<ChronicTrend[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [isAddingCondition, setIsAddingCondition] = useState(false);
  const [isAddingMeasurement, setIsAddingMeasurement] = useState(false);
  const [conditionLabel, setConditionLabel] = useState("");
  const [metricLabel, setMetricLabel] = useState("");
  const [measurementValue, setMeasurementValue] = useState("");
  const [unit, setUnit] = useState("");
  const [measuredAt, setMeasuredAt] = useState(localDateTimeNow);

  const selectedCondition = useMemo(
    () => conditions.find((condition) => condition.condition_id === selectedConditionId) ?? null,
    [conditions, selectedConditionId]
  );

  const loadConditionDetails = useCallback(async (conditionId: string) => {
    const [measurementResult, trendResult] = await Promise.all([
      listChronicMeasurements(conditionId),
      listChronicTrends(conditionId),
    ]);
    setMeasurements(measurementResult.items);
    setTrends(trendResult.items);
  }, []);

  const load = useCallback(async (preferredConditionId?: string | null) => {
    setState("loading");
    try {
      const result = await listChronicConditions();
      setConditions(result.items);
      const nextConditionId = preferredConditionId
        ?? selectedConditionId
        ?? result.items[0]?.condition_id
        ?? null;
      const resolvedId = result.items.some((item) => item.condition_id === nextConditionId)
        ? nextConditionId
        : result.items[0]?.condition_id ?? null;
      setSelectedConditionId(resolvedId);
      if (resolvedId) {
        await loadConditionDetails(resolvedId);
      } else {
        setMeasurements([]);
        setTrends([]);
      }
      setState("ready");
    } catch (error) {
      setState("error");
      toast.show(error instanceof Error ? error.message : "慢病记录暂时无法读取，请稍后重试");
    }
  }, [loadConditionDetails, selectedConditionId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  // The initial load must not be re-triggered by selecting a record.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectCondition = async (conditionId: string) => {
    if (conditionId === selectedConditionId || state === "loading") return;
    setSelectedConditionId(conditionId);
    setState("loading");
    try {
      await loadConditionDetails(conditionId);
      setState("ready");
    } catch (error) {
      setState("error");
      toast.show(error instanceof Error ? error.message : "该记录暂时无法读取，请稍后重试");
    }
  };

  const addCondition = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const label = conditionLabel.trim();
    if (!label || isAddingCondition) return;
    setIsAddingCondition(true);
    try {
      const created = await createChronicCondition(label);
      setConditionLabel("");
      await load(created.condition_id);
      toast.show("已保存为本人自述记录，尚未由医生确认");
    } catch (error) {
      toast.show(error instanceof Error ? error.message : "暂未能新建记录，请稍后重试");
    } finally {
      setIsAddingCondition(false);
    }
  };

  const addMeasurement = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedCondition || isAddingMeasurement) return;
    const value = Number(measurementValue);
    if (!metricLabel.trim() || !unit.trim() || !measurementValue.trim() || !Number.isFinite(value) || value < 0) {
      toast.show("请填写测量项目、非负数值和单位");
      return;
    }
    const date = new Date(measuredAt);
    if (Number.isNaN(date.getTime())) {
      toast.show("请填写有效的测量时间");
      return;
    }
    setIsAddingMeasurement(true);
    try {
      await addChronicMeasurement(selectedCondition.condition_id, {
        metric_label: metricLabel.trim(),
        value,
        unit: unit.trim(),
        measured_at: date.toISOString(),
      });
      setMeasurementValue("");
      setMeasuredAt(localDateTimeNow());
      await load(selectedCondition.condition_id);
      toast.show("测量值已记录，只会与同名项目的上次记录比较");
    } catch (error) {
      toast.show(error instanceof Error ? error.message : "测量值暂未保存，请稍后重试");
    } finally {
      setIsAddingMeasurement(false);
    }
  };

  const inputClassName = cn("h-11 text-base", seniorMode && "h-12 text-lg");
  const labelClassName = cn("text-sm", seniorMode && "text-lg");

  return (
    <section className={cn("mx-auto w-full max-w-4xl space-y-5 px-4 py-5 sm:px-6", seniorMode && "max-w-5xl py-6")} aria-labelledby="chronic-care-title">
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-primary">
          <ClipboardPlus className={cn("size-5", seniorMode && "size-6")} aria-hidden="true" />
          <h1 id="chronic-care-title" className={cn("font-semibold", seniorMode ? "text-2xl" : "text-xl")}>我的慢病记录</h1>
        </div>
        <p className={cn("text-muted-foreground", seniorMode ? "text-lg leading-8" : "text-sm leading-6")}>
          用于记录您自己描述的情况和测量值。系统只比较数值变化，不判断是否正常、不做诊断，也不能替代医生诊疗。
        </p>
      </div>

      <Card className="border-amber-300/70 bg-amber-50/60 dark:border-amber-800 dark:bg-amber-950/20">
        <CardContent className={cn("flex gap-3", seniorMode ? "text-lg leading-8" : "text-sm leading-6")}>
          <AlertCircle className="mt-0.5 size-5 shrink-0 text-amber-700 dark:text-amber-400" aria-hidden="true" />
          <p>若您出现胸痛、呼吸困难、意识异常、突发肢体无力或自伤想法，请立即联系急救服务或前往医疗机构，不要等待本页面的记录结果。</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className={cn(seniorMode && "text-xl")}>新建一项本人自述记录</CardTitle>
          <CardDescription className={cn(seniorMode && "text-lg leading-7")}>例如：高血压、糖尿病。保存后仍显示为“本人自述”。</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-3 sm:flex-row" onSubmit={addCondition}>
            <div className="min-w-0 flex-1">
              <Label htmlFor="chronic-condition-label" className="sr-only">本人自述的健康情况</Label>
              <Input id="chronic-condition-label" value={conditionLabel} onChange={(event) => setConditionLabel(event.target.value)} maxLength={80} placeholder="填写本人自述的健康情况" className={inputClassName} disabled={isAddingCondition} />
            </div>
            <Button type="submit" className={cn("min-h-11 gap-2", seniorMode && "min-h-12 px-5 text-lg")} disabled={!conditionLabel.trim() || isAddingCondition}>
              <Plus className="size-4" aria-hidden="true" />
              {isAddingCondition ? "正在保存" : "保存记录"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {state === "loading" && (
        <InlineLoadingState
          message="正在读取您的记录"
          className={cn("min-h-28", seniorMode && "text-lg")}
        />
      )}

      {state === "error" && (
        <Card className="border-destructive/40">
          <CardContent className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className={cn("text-destructive", seniorMode && "text-lg")}>记录暂时无法读取，请检查网络后重试。</p>
            <Button type="button" variant="outline" onClick={() => void load()} className={cn("min-h-11", seniorMode && "min-h-12 text-lg")}>重新读取</Button>
          </CardContent>
        </Card>
      )}

      {state === "ready" && conditions.length === 0 && (
        <Card className="border-dashed">
          <CardContent className={cn("py-8 text-center text-muted-foreground", seniorMode && "py-10 text-lg")}>还没有记录。先在上方填写一项您自己描述的健康情况。</CardContent>
        </Card>
      )}

      {state === "ready" && conditions.length > 0 && (
        <>
          <nav className="flex flex-wrap gap-2" aria-label="选择本人自述记录">
            {conditions.map((condition) => {
              const active = condition.condition_id === selectedConditionId;
              return (
                <Button key={condition.condition_id} type="button" variant={active ? "default" : "outline"} onClick={() => void selectCondition(condition.condition_id)} className={cn("min-h-11", seniorMode && "min-h-12 text-lg")} aria-pressed={active}>
                  {condition.label}
                </Button>
              );
            })}
          </nav>

          {selectedCondition && (
            <Card>
              <CardHeader>
                <CardTitle className={cn(seniorMode && "text-xl")}>{selectedCondition.label}</CardTitle>
                <CardDescription className={cn(seniorMode && "text-lg leading-7")}>本人自述，尚未由医生确认</CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" onSubmit={addMeasurement}>
                  <div className="space-y-2">
                    <Label htmlFor="chronic-metric-label" className={labelClassName}>测量项目</Label>
                    <Input id="chronic-metric-label" value={metricLabel} onChange={(event) => setMetricLabel(event.target.value)} placeholder="如：收缩压" maxLength={80} className={inputClassName} disabled={isAddingMeasurement} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="chronic-measurement-value" className={labelClassName}>数值</Label>
                    <Input id="chronic-measurement-value" type="number" min="0" step="any" inputMode="decimal" value={measurementValue} onChange={(event) => setMeasurementValue(event.target.value)} placeholder="如：120" className={inputClassName} disabled={isAddingMeasurement} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="chronic-unit" className={labelClassName}>单位</Label>
                    <Input id="chronic-unit" value={unit} onChange={(event) => setUnit(event.target.value)} placeholder="如：mmHg" maxLength={32} className={inputClassName} disabled={isAddingMeasurement} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="chronic-measured-at" className={labelClassName}>测量时间</Label>
                    <Input id="chronic-measured-at" type="datetime-local" value={measuredAt} onChange={(event) => setMeasuredAt(event.target.value)} className={inputClassName} disabled={isAddingMeasurement} />
                  </div>
                  <div className="sm:col-span-2 lg:col-span-4">
                    <Button type="submit" className={cn("min-h-11 gap-2", seniorMode && "min-h-12 px-5 text-lg")} disabled={isAddingMeasurement}>
                      <Plus className="size-4" aria-hidden="true" /> {isAddingMeasurement ? "正在记录" : "记录这次测量"}
                    </Button>
                  </div>
                </form>

                <div className="space-y-3 border-t pt-5">
                  <div className="flex items-center gap-2">
                    <BarChart3 className="size-5 text-primary" aria-hidden="true" />
                    <h2 className={cn("font-medium", seniorMode && "text-xl")}>同名项目的数值比较</h2>
                  </div>
                  <p className={cn("text-muted-foreground", seniorMode ? "text-lg leading-8" : "text-sm leading-6")}>只和同一测量项目的上一次记录比较；“高/低”不代表病情变化或风险。</p>
                  {trends.length === 0 ? <p className={cn("text-muted-foreground", seniorMode && "text-lg")}>记录测量值后，这里会显示纯数值比较。</p> : (
                    <ul className="grid gap-3 sm:grid-cols-2">
                      {trends.map((trend) => <li key={`${trend.metric_label}:${trend.unit}`} className="rounded-lg border bg-muted/30 p-3">
                        <p className={cn("font-medium", seniorMode && "text-lg")}>{trend.metric_label}：{formatValue(trend.latest_value)} {trend.unit}</p>
                        <p className={cn("mt-1 text-muted-foreground", seniorMode ? "text-lg" : "text-sm")}>{directionLabel[trend.direction]}</p>
                      </li>)}
                    </ul>
                  )}
                </div>

                <div className="space-y-3 border-t pt-5">
                  <h2 className={cn("font-medium", seniorMode && "text-xl")}>已记录的测量值</h2>
                  {measurements.length === 0 ? <p className={cn("text-muted-foreground", seniorMode && "text-lg")}>还没有测量值。</p> : (
                    <ul className="divide-y rounded-lg border">
                      {measurements.map((measurement) => <li key={measurement.measurement_id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-3 py-3">
                        <span className={cn("font-medium", seniorMode && "text-lg")}>{measurement.metric_label}：{formatValue(measurement.value)} {measurement.unit}</span>
                        <time dateTime={measurement.measured_at} className={cn("text-muted-foreground", seniorMode ? "text-base" : "text-sm")}>{formatDateTime(measurement.measured_at)}</time>
                      </li>)}
                    </ul>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </section>
  );
}
