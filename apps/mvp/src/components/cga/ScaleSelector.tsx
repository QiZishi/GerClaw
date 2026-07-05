"use client";

import { Brain, Clock, HelpCircle, ListChecks } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import type { Scale } from "@/types";

interface ScaleSelectorProps {
  scales: Scale[];
  onSelect?: (scale: Scale) => void;
}

/**
 * §7 CGA 评估 — 量表选择卡片网格
 * 每张卡显示名称/题目数/预计时长/适用场景
 */
export function ScaleSelector({ scales, onSelect }: ScaleSelectorProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);

  return (
    <div className="space-y-2">
      <div className="text-sm text-muted-foreground">
        请选择需要进行的评估量表：
      </div>
      <div className="grid grid-cols-1 gap-2">
        {scales.map((scale) => (
          <button
            key={scale.id}
            type="button"
            onClick={() => onSelect?.(scale)}
            className={cn(
              "flex flex-col gap-1.5 rounded-lg border border-border bg-card p-3 text-left hover:border-primary/40 hover:bg-muted/40 transition-colors",
              seniorMode && "p-4"
            )}
            aria-label={`选择量表 ${scale.fullName}`}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <div className="flex items-center justify-center size-7 rounded-md bg-primary/10 text-primary shrink-0">
                  <Brain className="size-3.5" />
                </div>
                <div className="min-w-0">
                  <div
                    className={cn(
                      "font-medium truncate",
                      seniorMode ? "text-base" : "text-sm"
                    )}
                  >
                    {scale.fullName}
                  </div>
                  <div className="text-[11px] text-muted-foreground truncate">
                    {scale.name} · {scale.category}
                  </div>
                </div>
              </div>
              <Badge variant="outline" className="shrink-0 text-[10px]">
                {scale.questionCount} 题
              </Badge>
            </div>
            <div className="text-xs text-muted-foreground leading-relaxed">
              {scale.description}
            </div>
            <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
              <span className="flex items-center gap-0.5">
                <ListChecks className="size-3" />
                {scale.questionCount} 题
              </span>
              <span className="flex items-center gap-0.5">
                <Clock className="size-3" />
                约 {scale.estimatedMinutes} 分钟
              </span>
              {scale.grading.thresholds.length > 0 && (
                <span className="flex items-center gap-0.5">
                  <HelpCircle className="size-3" />
                  {scale.grading.thresholds.length} 级评分
                </span>
              )}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
