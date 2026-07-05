"use client";

import { useState } from "react";
import { Activity, Clock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Disclaimer } from "@/components/prescription/Disclaimer";
import { formatDate } from "@/lib/format";
import { mockCGAReport, mockScaleResults } from "@/data/mock/cga";
import type { ScaleResult } from "@/types";

interface DoctorCGAWorkspaceProps {
  patientName?: string;
}

/**
 * §7 CGA 评估 — 医生端工作区
 * 患者评估进度时间线 + 各量表结果汇总卡片 + 历史对比折线图占位
 */
export function DoctorCGAWorkspace({ patientName }: DoctorCGAWorkspaceProps) {
  const report = mockCGAReport;
  const name = patientName ?? report.patientName ?? "张桂芳";

  // 时间线基准时间在挂载时确定一次（避免渲染期调用 Date.now 不纯）
  const [baseNow] = useState(() => Date.now());
  const timeline = [
    {
      date: baseNow - 90 * 86400_000,
      event: "首次 CGA 评估",
      detail: "PHQ-9 评分 12 分（中度抑郁倾向）",
      status: "done" as const,
    },
    {
      date: baseNow - 60 * 86400_000,
      event: "复评 + 干预方案调整",
      detail: "PHQ-9 评分 9 分（轻度抑郁）",
      status: "done" as const,
    },
    {
      date: baseNow - 30 * 86400_000,
      event: "MMSE 神经评估",
      detail: "MMSE 24 分（轻度认知障碍）",
      status: "done" as const,
    },
    {
      date: report.createdAt,
      event: "本次综合评估",
      detail: "综合评分 65 分（中等风险）",
      status: "current" as const,
    },
  ];

  // 历史对比数据（mock）
  const historyTrend = [
    { label: "首次", score: 58 },
    { label: "1月后", score: 62 },
    { label: "2月后", score: 65 },
    { label: "本次", score: 65 },
  ];
  const maxScore = Math.max(...historyTrend.map((h) => h.score));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold flex items-center gap-1.5">
            <Activity className="size-4 text-primary" />
            CGA 工作区
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">
            患者：{name} · {report.patientAge} 岁
          </div>
        </div>
        <Badge variant="secondary">综合风险：中等</Badge>
      </div>

      <Separator />

      {/* 评估进度时间线 */}
      <div>
        <div className="text-xs font-medium text-muted-foreground mb-2">
          评估进度时间线
        </div>
        <ol className="space-y-2 relative border-l border-border pl-4">
          {timeline.map((t, i) => (
            <li key={i} className="relative">
              <span
                className={
                  "absolute -left-[21px] top-1 size-2.5 rounded-full border-2 " +
                  (t.status === "current"
                    ? "border-primary bg-primary"
                    : "border-muted-foreground bg-background")
                }
                aria-hidden
              />
              <div className="flex items-center gap-2">
                <Clock className="size-3 text-muted-foreground" />
                <span className="text-[11px] text-muted-foreground">
                  {formatDate(t.date)}
                </span>
                {t.status === "current" && (
                  <Badge variant="default" className="text-[10px]">
                    当前
                  </Badge>
                )}
              </div>
              <div className="text-sm font-medium mt-0.5">{t.event}</div>
              <div className="text-xs text-muted-foreground">{t.detail}</div>
            </li>
          ))}
        </ol>
      </div>

      <Separator />

      {/* 各量表结果汇总 */}
      <div>
        <div className="text-xs font-medium text-muted-foreground mb-2">
          量表结果汇总
        </div>
        <div className="grid grid-cols-1 gap-1.5">
          {mockScaleResults.map((r) => (
            <SummaryRow key={r.scaleId} result={r} />
          ))}
        </div>
      </div>

      <Separator />

      {/* 历史对比折线图（占位） */}
      <div>
        <div className="text-xs font-medium text-muted-foreground mb-2">
          综合评分历史对比
        </div>
        <div className="rounded-lg border border-border bg-muted/30 p-3">
          <div className="flex items-end justify-around gap-2 h-24">
            {historyTrend.map((h) => {
              const height = (h.score / maxScore) * 100;
              return (
                <div
                  key={h.label}
                  className="flex flex-col items-center gap-1 flex-1"
                >
                  <div className="text-[10px] text-muted-foreground">
                    {h.score}
                  </div>
                  <div
                    className="w-full rounded-t bg-primary/60"
                    style={{ height: `${height}%`, minHeight: 4 }}
                    aria-label={`${h.label}：${h.score} 分`}
                  />
                  <div className="text-[10px] text-muted-foreground">
                    {h.label}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="text-[10px] text-muted-foreground text-center mt-2">
            评分呈稳定趋势，建议持续监测
          </div>
        </div>
      </div>

      <Disclaimer text={report.disclaimer} />
    </div>
  );
}

function SummaryRow({ result }: { result: ScaleResult }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-md border border-border bg-card px-2.5 py-1.5">
      <div className="min-w-0">
        <div className="text-xs font-medium truncate">{result.scaleName}</div>
        <div className="text-[10px] text-muted-foreground truncate">
          {result.interpretation}
        </div>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <span className="text-[11px] tabular-nums">
          {result.totalScore}/{result.maxScore}
        </span>
        <Badge
          variant={
            /重度|严重|障碍|差/.test(result.level)
              ? "destructive"
              : /轻度|中|一般/.test(result.level)
                ? "default"
                : "secondary"
          }
          className="text-[10px]"
        >
          {result.level}
        </Badge>
      </div>
    </div>
  );
}
