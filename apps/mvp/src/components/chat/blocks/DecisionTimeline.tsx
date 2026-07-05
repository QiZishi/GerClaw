"use client";

import { useState } from "react";
import {
  Check,
  ChevronDown,
  Eye,
  Lightbulb,
  Loader2,
  Play,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { formatDuration } from "@/lib/format";
import type { DecisionStep } from "@/types";

interface DecisionTimelineProps {
  data: DecisionStep[];
}

/**
 * §4.2.3 决策时间线（ReAct Thought/Action/Observation）
 * 垂直时间线，每步骤图标 + 名称 + 状态 + 耗时
 * 已完成打勾，失败标红，当前执行高亮
 */
export function DecisionTimeline({ data }: DecisionTimelineProps) {
  const [expanded, setExpanded] = useState(true);

  if (!data || data.length === 0) return null;

  // 当前执行步骤：最后一个 running 状态的步骤
  const currentRunningIdx = data.findIndex((s) => s.status === "running");

  return (
    <div className="rounded-lg border border-border bg-muted/30 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-muted/50 transition-colors"
        aria-expanded={expanded}
      >
        <span className="flex items-center gap-2 text-sm">
          <Play className="size-4 text-muted-foreground" />
          <span className="font-medium">决策过程</span>
          <span className="text-xs text-muted-foreground">
            · {data.length} 步
          </span>
        </span>
        <ChevronDown
          className={cn(
            "size-4 text-muted-foreground transition-transform",
            expanded && "rotate-180"
          )}
        />
      </button>
      {expanded && (
        <div className="border-t border-border/60 px-3 py-2">
          <div className="relative">
            {data.map((step, idx) => {
              const isLast = idx === data.length - 1;
              const isCurrent = idx === currentRunningIdx;
              return (
                <div
                  key={step.id}
                  className="relative flex gap-3 pb-4 last:pb-0"
                >
                  {/* 垂直连接线 */}
                  {!isLast && (
                    <div
                      className="absolute left-[11px] top-6 bottom-0 w-px bg-border"
                      aria-hidden
                    />
                  )}
                  {/* 图标 */}
                  <div
                    className={cn(
                      "relative z-10 flex size-6 shrink-0 items-center justify-center rounded-full border-2 bg-background",
                      step.status === "done" &&
                        "border-green-500 text-green-600",
                      step.status === "failed" &&
                        "border-destructive text-destructive",
                      step.status === "running" &&
                        "border-blue-500 text-blue-600"
                    )}
                  >
                    <StepTypeIcon type={step.type} status={step.status} />
                  </div>
                  {/* 内容 */}
                  <div
                    className={cn(
                      "flex-1 min-w-0",
                      isCurrent && "bg-blue-50 dark:bg-blue-950/30 rounded-md px-2 py-1 -mx-1"
                    )}
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium">
                        {step.title}
                      </span>
                      <Badge
                        variant="outline"
                        className="text-[10px] py-0 h-4"
                      >
                        {step.type === "thought"
                          ? "思考"
                          : step.type === "action"
                            ? "行动"
                            : "观察"}
                      </Badge>
                      <StepStatusBadge status={step.status} />
                      {step.durationMs !== undefined && (
                        <span className="text-xs text-muted-foreground">
                          {formatDuration(step.durationMs)}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                      {step.content}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function StepTypeIcon({
  type,
  status,
}: {
  type: DecisionStep["type"];
  status: DecisionStep["status"];
}) {
  if (status === "running") {
    return <Loader2 className="size-3 animate-spin" />;
  }
  if (status === "failed") {
    return <X className="size-3" />;
  }
  if (status === "done") {
    return <Check className="size-3" />;
  }
  // 默认按类型显示
  if (type === "thought") return <Lightbulb className="size-3" />;
  if (type === "action") return <Play className="size-3" />;
  return <Eye className="size-3" />;
}

function StepStatusBadge({ status }: { status: DecisionStep["status"] }) {
  switch (status) {
    case "running":
      return (
        <Badge variant="secondary" className="text-blue-600 h-5">
          运行中
        </Badge>
      );
    case "done":
      return (
        <Badge variant="secondary" className="text-green-600 h-5">
          完成
        </Badge>
      );
    case "failed":
      return <Badge variant="destructive" className="h-5">失败</Badge>;
  }
}
