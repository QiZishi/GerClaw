"use client";

import { Brain, Clock, ListChecks } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import type { Scale } from "@/types";

interface ScaleSelectorProps {
  scales: Scale[];
  selectedScaleIds?: string[];
  onSelectionChange?: (ids: string[]) => void;
  completedScaleIds?: string[];
  onStart?: () => void;
  onGenerateReport?: () => void;
  mode?: 'select' | 'continue';
  singleSelect?: boolean;
  onSelect?: (scale: Scale) => void;
}

export function ScaleSelector({
  scales,
  selectedScaleIds = [],
  onSelectionChange = () => {},
  completedScaleIds = [],
  onStart = () => {},
  onGenerateReport = () => {},
  mode = 'select',
  singleSelect = false,
  onSelect,
}: ScaleSelectorProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);

  if (singleSelect && onSelect) {
    return (
      <div className="grid grid-cols-1 gap-3">
        {scales.map((scale) => (
          <button
            key={scale.id}
            type="button"
            onClick={() => onSelect(scale)}
            className={cn(
              "flex items-start gap-3 rounded-lg border bg-card p-3 transition-colors text-left hover:border-primary/40 hover:bg-muted/40 cursor-pointer",
              seniorMode && "p-4"
            )}
          >
            <div className="flex items-center justify-center size-7 rounded-md bg-primary/10 text-primary shrink-0 mt-0.5">
              <Brain className="size-3.5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2 mb-1">
                <div className={cn("font-medium", seniorMode ? "text-base" : "text-sm")}>
                  {scale.fullName}
                </div>
                <Badge variant="outline" className="shrink-0 text-[10px]">
                  {scale.questionCount} 题
                </Badge>
              </div>
              <div className="text-xs text-muted-foreground leading-relaxed mb-2">
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
              </div>
            </div>
          </button>
        ))}
      </div>
    );
  }

  const allCompleted = scales.every((s) => completedScaleIds.includes(s.id));
  const selectableScales = mode === 'continue'
    ? scales.filter((s) => !completedScaleIds.includes(s.id))
    : scales;
  const allSelected = selectableScales.length > 0 &&
    selectableScales.every((s) => selectedScaleIds.includes(s.id));

  const handleToggleAll = () => {
    if (allSelected) {
      onSelectionChange([]);
    } else {
      onSelectionChange(selectableScales.map((s) => s.id));
    }
  };

  const handleToggleScale = (scaleId: string, checked: boolean) => {
    if (completedScaleIds.includes(scaleId)) return;
    if (checked) {
      onSelectionChange([...selectedScaleIds, scaleId]);
    } else {
      onSelectionChange(selectedScaleIds.filter((id) => id !== scaleId));
    }
  };

  const totalQuestions = selectedScaleIds.reduce((sum, id) => {
    const scale = scales.find((s) => s.id === id);
    return sum + (scale?.questionCount ?? 0);
  }, 0);
  const totalTime = selectedScaleIds.reduce((sum, id) => {
    const scale = scales.find((s) => s.id === id);
    return sum + (scale?.estimatedMinutes ?? 0);
  }, 0);

  if (allCompleted) {
    return (
      <div className="space-y-6">
        <div className="text-center py-8">
          <div className="text-5xl mb-4">🎉</div>
          <h3 className={cn("font-semibold mb-2", seniorMode ? "text-xl" : "text-lg")}>
            所有量表已作答完毕
          </h3>
          <p className={cn("text-muted-foreground", seniorMode ? "text-base" : "text-sm")}>
            您已完成全部 {scales.length} 个量表的评估
          </p>
        </div>
        <Button
          onClick={onGenerateReport}
          className={cn("w-full", seniorMode ? "h-14 text-lg" : "h-11")}
        >
          📊 生成评估报告
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          {mode === 'continue'
            ? `已完成 ${completedScaleIds.length} 个，还剩 ${selectableScales.length} 个量表可作答`
            : `请选择需要进行的评估量表（可多选）`}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleToggleAll}
          className={cn("text-primary", seniorMode && "text-base h-10")}
        >
          {allSelected ? "取消全选" : "全选"}
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-3">
        {scales.map((scale) => {
          const isCompleted = completedScaleIds.includes(scale.id);
          const isSelected = selectedScaleIds.includes(scale.id);
          return (
            <label
              key={scale.id}
              className={cn(
                "flex items-start gap-3 rounded-lg border bg-card p-3 transition-colors cursor-pointer",
                !isCompleted && "hover:border-primary/40 hover:bg-muted/40",
                isSelected && !isCompleted && "border-primary bg-primary/5",
                isCompleted && "border-green-200 bg-green-50 dark:border-green-900/40 dark:bg-green-950/20 opacity-70",
                seniorMode && "p-4"
              )}
            >
              <Checkbox
                checked={isSelected || isCompleted}
                onCheckedChange={(checked) => handleToggleScale(scale.id, checked as boolean)}
                disabled={isCompleted}
                className={cn("mt-0.5", seniorMode && "size-5")}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2 mb-1">
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
                  {isCompleted ? (
                    <Badge className="shrink-0 text-[10px] bg-green-500 hover:bg-green-600 text-white">
                      ✓ 已作答
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="shrink-0 text-[10px]">
                      {scale.questionCount} 题
                    </Badge>
                  )}
                </div>
                <div className="text-xs text-muted-foreground leading-relaxed mb-2">
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
                </div>
              </div>
            </label>
          );
        })}
      </div>

      <div className="pt-2 border-t border-border">
        <div className="flex items-center justify-between mb-3">
          <div className={cn("text-muted-foreground", seniorMode ? "text-base" : "text-sm")}>
            已选择 {selectedScaleIds.length} 个量表
            {selectedScaleIds.length > 0 && (
              <span> · 共 {totalQuestions} 题 · 约 {totalTime} 分钟</span>
            )}
          </div>
        </div>
        <Button
          onClick={onStart}
          disabled={selectedScaleIds.length === 0}
          className={cn("w-full", seniorMode ? "h-14 text-lg" : "h-11")}
        >
          开始作答
        </Button>
      </div>
    </div>
  );
}
