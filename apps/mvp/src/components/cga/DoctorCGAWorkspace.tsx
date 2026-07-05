"use client";

import { Activity, Clock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Disclaimer } from "@/components/prescription/Disclaimer";
import { formatDate } from "@/lib/format";
import type { ScaleResult } from "@/types";

interface DoctorCGAWorkspaceProps {
  patientName?: string;
}

/**
 * §7 CGA 评估 — 医生端工作区
 * 患者评估进度时间线 + 各量表结果汇总卡片 + 历史对比折线图占位
 */
export function DoctorCGAWorkspace({ patientName }: DoctorCGAWorkspaceProps) {
  const name = patientName ?? "未选择患者";
  const scaleResults: ScaleResult[] = [];

  const timeline: { date: number; event: string; detail: string; status: "done" | "current" }[] = [];

  const historyTrend: { label: string; score: number }[] = [];
  const maxScore = 100;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold flex items-center gap-1.5">
            <Activity className="size-4 text-primary" />
            CGA 工作区
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">
            患者：{name}
          </div>
        </div>
        <Badge variant="secondary">暂无数据</Badge>
      </div>

      <Separator />

      <div>
        <div className="text-xs font-medium text-muted-foreground mb-2">
          评估进度时间线
        </div>
        {timeline.length === 0 ? (
          <div className="text-xs text-muted-foreground py-2">暂无评估记录</div>
        ) : (
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
        )}
      </div>

      <Separator />

      <div>
        <div className="text-xs font-medium text-muted-foreground mb-2">
          量表结果汇总
        </div>
        {scaleResults.length === 0 ? (
          <div className="text-xs text-muted-foreground py-2">暂无量表结果</div>
        ) : (
          <div className="grid grid-cols-1 gap-1.5">
            {scaleResults.map((r) => (
              <SummaryRow key={r.scaleId} result={r} />
            ))}
          </div>
        )}
      </div>

      <Separator />

      <div>
        <div className="text-xs font-medium text-muted-foreground mb-2">
          综合评分历史对比
        </div>
        <div className="rounded-lg border border-border bg-muted/30 p-3">
          <div className="flex items-end justify-around gap-2 h-24">
            {historyTrend.length === 0 ? (
              <div className="text-xs text-muted-foreground self-center">暂无历史数据</div>
            ) : (
              historyTrend.map((h) => {
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
              })
            )}
          </div>
        </div>
      </div>

      <Disclaimer text="内容由 AI 生成，仅供参考。身体不适请及时就医。" />
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
