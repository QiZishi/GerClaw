"use client";

import { AlertTriangle, BookOpen, CheckCircle2, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Disclaimer } from "@/components/prescription/Disclaimer";
import { cn } from "@/lib/utils";
import type { DrugReviewResult as DrugReviewResultData, RiskLevel } from "@/types";

interface DrugReviewResultViewProps {
  result: DrugReviewResultData;
}

const RISK_META: Record<
  RiskLevel,
  { label: string; cls: string; variant: "default" | "secondary" | "destructive" | "outline" }
> = {
  safe: {
    label: "安全",
    cls: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-200",
    variant: "secondary",
  },
  caution: {
    label: "谨慎",
    cls: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200",
    variant: "outline",
  },
  warning: {
    label: "警示",
    cls: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-200",
    variant: "default",
  },
  contraindicated: {
    label: "禁忌",
    cls: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-200",
    variant: "destructive",
  },
  severe: {
    label: "严重",
    cls: "bg-red-200 text-red-800 dark:bg-red-900/60 dark:text-red-100",
    variant: "destructive",
  },
};

/**
 * §4.1 用药审查结果展示
 * 总体风险徽章 + DDI + Beers + 剂量 + 建议 + Disclaimer
 */
export function DrugReviewResultView({ result }: DrugReviewResultViewProps) {
  const overall = RISK_META[result.overallRisk];

  return (
    <div className="space-y-3">
      {/* 总体风险 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <ShieldAlert className="size-4 text-primary" />
          <span className="text-sm font-semibold">用药审查结果</span>
        </div>
        <span
          className={cn(
            "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
            overall.cls
          )}
        >
          总体风险：{overall.label}
        </span>
      </div>

      {/* 摘要 */}
      <div className="rounded-lg border border-border bg-muted/30 p-3">
        <div className="text-xs font-medium text-muted-foreground mb-1">
          审查摘要
        </div>
        <p className="text-xs leading-relaxed">{result.summary}</p>
        <div className="flex flex-wrap gap-3 mt-2 text-[11px] text-muted-foreground">
          <span>评估药物：{result.drugs.length} 种</span>
          <span>DDI：{result.ddiResults.length} 对</span>
          <span>Beers：{result.beersResults.length} 条</span>
          <span>剂量：{result.dosageResults.length} 条</span>
        </div>
      </div>

      <Separator />

      {/* DDI 结果 */}
      <Section title="药物相互作用（DDI）" count={result.ddiResults.length}>
        {result.ddiResults.length === 0 ? (
          <EmptyRow icon="check" text="未发现药物相互作用" />
        ) : (
          result.ddiResults.map((d, i) => {
            const meta = RISK_META[d.severity];
            return (
              <div
                key={i}
                className="rounded-lg border border-border bg-card p-2.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">
                    {d.drugA} + {d.drugB}
                  </span>
                  <Badge variant={meta.variant} className="text-[10px]">
                    {meta.label}
                  </Badge>
                </div>
                <div className="text-xs text-muted-foreground mt-1 leading-relaxed">
                  <div>机制：{d.mechanism}</div>
                  <div>临床效应：{d.clinicalEffect}</div>
                </div>
                <div className="text-[11px] text-amber-700 dark:text-amber-300 mt-1">
                  建议：{d.recommendation}
                </div>
                {d.evidenceSource && (
                  <div className="text-[10px] text-muted-foreground mt-1 flex items-center gap-0.5">
                    <BookOpen className="size-2.5" />
                    {d.evidenceSource}
                  </div>
                )}
              </div>
            );
          })
        )}
      </Section>

      {/* Beers 结果 */}
      <Section title="Beers 标准警示" count={result.beersResults.length}>
        {result.beersResults.length === 0 ? (
          <EmptyRow icon="check" text="未发现 Beers 标准警示" />
        ) : (
          result.beersResults.map((b, i) => {
            const meta = RISK_META[b.severity];
            return (
              <div
                key={i}
                className="rounded-lg border border-border bg-card p-2.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{b.drug}</span>
                  <Badge variant={meta.variant} className="text-[10px]">
                    {meta.label}
                  </Badge>
                </div>
                <div className="text-[11px] text-muted-foreground mt-0.5">
                  {b.category}
                </div>
                <div className="text-xs text-muted-foreground mt-1 leading-relaxed">
                  原因：{b.reason}
                </div>
                <div className="text-[11px] text-amber-700 dark:text-amber-300 mt-1">
                  建议：{b.recommendation}
                </div>
                {b.alternative && b.alternative.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    <span className="text-[10px] text-muted-foreground">
                      替代：
                    </span>
                    {b.alternative.map((a) => (
                      <Badge
                        key={a}
                        variant="outline"
                        className="text-[10px] bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-200"
                      >
                        {a}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </Section>

      {/* 剂量结果 */}
      <Section title="剂量校验" count={result.dosageResults.length}>
        {result.dosageResults.length === 0 ? (
          <EmptyRow icon="check" text="剂量均在推荐范围" />
        ) : (
          result.dosageResults.map((d, i) => {
            const isOk = d.status === "ok";
            return (
              <div
                key={i}
                className="rounded-lg border border-border bg-card p-2.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{d.drug}</span>
                  <Badge
                    variant={isOk ? "secondary" : "destructive"}
                    className="text-[10px]"
                  >
                    {isOk ? "正常" : d.status === "too-high" ? "偏高" : d.status === "too-low" ? "偏低" : "未知"}
                  </Badge>
                </div>
                <div className="text-xs text-muted-foreground mt-1 space-y-0.5">
                  <div>处方剂量：{d.prescribedDose}</div>
                  <div>推荐范围：{d.recommendedRange}</div>
                </div>
                {d.recommendation && (
                  <div className="text-[11px] text-amber-700 dark:text-amber-300 mt-1">
                    {d.recommendation}
                  </div>
                )}
              </div>
            );
          })
        )}
      </Section>

      <Separator />

      {/* 总体建议 */}
      <div className="space-y-1.5">
        <div className="text-xs font-medium text-muted-foreground">总体建议</div>
        <ul className="text-xs space-y-1 list-disc pl-4">
          {result.recommendations.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      </div>

      <Disclaimer text={result.disclaimer} />

      {(result.ddiResults.some((d) => d.severity === "contraindicated" || d.severity === "severe") ||
        result.beersResults.some((b) => b.severity === "contraindicated")) && (
        <div className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-red-800 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200">
          <AlertTriangle className="size-4 shrink-0 mt-0.5" />
          <p className="text-xs">
            检测到严重药物风险，请立即与主治医生沟通调整方案。
          </p>
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">{title}</span>
        <Badge variant="outline" className="text-[10px]">
          {count}
        </Badge>
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function EmptyRow({ icon, text }: { icon: "check" | "alert"; text: string }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-dashed border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
      {icon === "check" ? (
        <CheckCircle2 className="size-3.5 text-green-600" />
      ) : (
        <AlertTriangle className="size-3.5 text-amber-600" />
      )}
      {text}
    </div>
  );
}
