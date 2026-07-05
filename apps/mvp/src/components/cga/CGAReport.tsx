"use client";

import { AlertTriangle, ClipboardCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Disclaimer } from "@/components/prescription/Disclaimer";
import { cn } from "@/lib/utils";
import type { CGAReport as CGAReportData, ScaleResult } from "@/types";

interface CGAReportProps {
  report: CGAReportData;
  /** 单独的量表结果（可选，优先于 report.scaleResults） */
  results?: ScaleResult[];
}

const RISK_COLORS: Record<string, string> = {
  low: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-200",
  moderate:
    "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-200",
  high: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-200",
};

const LEVEL_BADGE: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  正常: "secondary",
  良好: "secondary",
  良: "secondary",
  无: "secondary",
};

function levelVariant(level: string): "default" | "secondary" | "destructive" | "outline" {
  if (/重度|严重|障碍|差|高/.test(level)) return "destructive";
  if (/轻度|中|一般/.test(level)) return "default";
  return LEVEL_BADGE[level] ?? "outline";
}

/**
 * §7 CGA 评估报告
 * 各量表得分/分级/解读/建议
 */
export function CGAReport({ report, results }: CGAReportProps) {
  const scaleResults = results ?? report.scaleResults;
  const riskClass = RISK_COLORS[report.riskLevel] ?? RISK_COLORS.moderate;

  return (
    <div className="space-y-3">
      {/* 头部 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <ClipboardCheck className="size-4 text-primary" />
          <span className="text-sm font-semibold">CGA 综合评估报告</span>
        </div>
        <span
          className={cn(
            "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
            riskClass
          )}
        >
          风险：{report.riskLevel === "low" ? "低" : report.riskLevel === "moderate" ? "中" : "高"}
        </span>
      </div>

      {report.patientName && (
        <div className="text-xs text-muted-foreground">
          患者：{report.patientName}
          {report.patientAge ? ` · ${report.patientAge} 岁` : ""}
        </div>
      )}

      {/* 汇总 */}
      <div className="rounded-lg border border-border bg-muted/30 p-3">
        <div className="text-xs font-medium text-muted-foreground mb-1">
          综合评估
        </div>
        <p className="text-xs leading-relaxed">{report.summary}</p>
      </div>

      <Separator />

      {/* 各量表结果 */}
      <div className="space-y-2">
        <div className="text-xs font-medium text-muted-foreground">
          量表评估明细
        </div>
        {scaleResults.map((r) => (
          <ScaleResultCard key={r.scaleId} result={r} />
        ))}
      </div>

      <Separator />

      {/* 建议 */}
      <div className="space-y-1.5">
        <div className="text-xs font-medium text-muted-foreground">建议</div>
        <ul className="text-xs space-y-1 list-disc pl-4">
          {report.recommendations.map((rec, i) => (
            <li key={i}>{rec}</li>
          ))}
        </ul>
      </div>

      <Disclaimer text={report.disclaimer} />

      {report.riskLevel === "high" && (
        <div className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-red-800 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200">
          <AlertTriangle className="size-4 shrink-0 mt-0.5" />
          <p className="text-xs">
            该患者综合风险等级较高，建议尽快就医进行详细评估与干预。
          </p>
        </div>
      )}
    </div>
  );
}

function ScaleResultCard({ result }: { result: ScaleResult }) {
  return (
    <div className="rounded-lg border border-border bg-card p-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">{result.scaleName}</span>
        <Badge variant={levelVariant(result.level)} className="text-[10px]">
          {result.level}
        </Badge>
      </div>
      <div className="flex items-center gap-2 mt-1 text-[11px] text-muted-foreground">
        <span>
          得分：{result.totalScore} / {result.maxScore}
        </span>
      </div>
      <p className="text-xs leading-relaxed mt-1.5 text-muted-foreground">
        {result.interpretation}
      </p>
    </div>
  );
}
