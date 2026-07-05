"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import type { Scale, ScaleResult } from "@/types";

interface CGAConversationProps {
  scale: Scale;
  onComplete?: (result: ScaleResult) => void;
  onExit?: () => void;
}

/**
 * §7 CGA 评估 — 答题界面
 * 题目进度条 + 当前题目 + 选项卡片 + 上一题/下一题
 * 最后一题提交触发 onComplete
 */
export function CGAConversation({ scale, onComplete, onExit }: CGAConversationProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const [idx, setIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<string, number | string>>({});

  const total = scale.questions.length;
  const current = scale.questions[idx];
  const progress = ((idx + 1) / total) * 100;
  const isLast = idx === total - 1;
  const answered = current ? answers[current.id] !== undefined : false;

  const handleSelect = (value: number | string) => {
    if (!current) return;
    setAnswers((a) => ({ ...a, [current.id]: value }));
  };

  const handleSubmit = () => {
    const totalScore = Object.entries(answers).reduce((sum, [, v]) => {
      const n = typeof v === "number" ? v : Number(v);
      return sum + (Number.isFinite(n) ? n : 0);
    }, 0);
    const maxScore = scale.questions.reduce(
      (s, q) => s + (q.maxValue ?? 0),
      0
    );
    const matched = [...scale.grading.thresholds]
      .sort((a, b) => a.max - b.max)
      .find((t) => totalScore <= t.max);
    const result: ScaleResult = {
      scaleId: scale.id,
      scaleName: scale.fullName,
      totalScore,
      maxScore,
      level: matched?.level ?? "未知",
      interpretation: matched?.interpretation ?? "",
      answers,
      completedAt: Date.now(),
    };
    onComplete?.(result);
  };

  if (!current) {
    return <div className="text-sm text-muted-foreground">该量表无题目</div>;
  }

  return (
    <div className="flex flex-col gap-3">
      {/* 顶部：量表名 + 退出 */}
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className={cn("font-medium truncate", seniorMode ? "text-base" : "text-sm")}>
            {scale.fullName}
          </div>
          <div className="text-[11px] text-muted-foreground">
            第 {idx + 1} / {total} 题
          </div>
        </div>
        {onExit && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onExit}
            className="shrink-0"
            aria-label="退出答题"
          >
            退出
          </Button>
        )}
      </div>

      <Progress value={progress} />

      {/* 题目 */}
      <div
        className={cn(
          "rounded-lg border border-border bg-card p-3",
          seniorMode && "p-4"
        )}
      >
        <div className="text-xs text-muted-foreground mb-1">
          题 {idx + 1}
          {current.required && <span className="text-destructive ml-1">*</span>}
        </div>
        <div
          className={cn(
            "font-medium leading-relaxed",
            seniorMode ? "text-lg" : "text-sm"
          )}
        >
          {current.text}
        </div>
        {current.hint && (
          <div className="mt-1.5 text-[11px] text-amber-700 dark:text-amber-300">
            提示：{current.hint}
          </div>
        )}
      </div>

      {/* 选项 */}
      <div className="grid grid-cols-1 gap-1.5">
        {current.options?.map((opt) => {
          const selected = answers[current.id] === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => handleSelect(opt.value)}
              className={cn(
                "flex items-center gap-2 rounded-lg border px-3 py-2 text-left transition-colors",
                seniorMode && "py-2.5 text-base",
                selected
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border bg-background hover:bg-muted"
              )}
              aria-pressed={selected}
            >
              <span
                className={cn(
                  "flex items-center justify-center size-5 rounded-full border text-[10px] font-medium shrink-0",
                  selected
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border text-muted-foreground"
                )}
              >
                {selected ? <Check className="size-3" /> : opt.value}
              </span>
              <span className="flex-1 text-sm">{opt.label}</span>
              {opt.description && (
                <span className="text-[11px] text-muted-foreground">
                  {opt.description}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* 导航 */}
      <div className="flex items-center justify-between gap-2 pt-1">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setIdx((i) => Math.max(0, i - 1))}
          disabled={idx === 0}
          className="gap-1"
        >
          <ChevronLeft className="size-3.5" />
          上一题
        </Button>
        {isLast ? (
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={!answered}
            className="gap-1"
          >
            <Check className="size-3.5" />
            提交
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={() => setIdx((i) => Math.min(total - 1, i + 1))}
            disabled={!answered}
            className="gap-1"
          >
            下一题
            <ChevronRight className="size-3.5" />
          </Button>
        )}
      </div>
    </div>
  );
}
