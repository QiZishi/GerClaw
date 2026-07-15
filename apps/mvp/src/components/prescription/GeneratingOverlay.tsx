"use client";

import { useEffect, useState } from "react";
import { Activity, ClipboardCheck, Loader2, Pill, Search } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";

interface GeneratingOverlayProps {
  /** 完成回调，默认 6s 后触发 */
  onDone?: () => void;
  /** 总时长 ms，默认 6000 */
  durationMs?: number;
}

const STAGES = [
  { icon: Activity, label: "正在分析患者信息…" },
  { icon: Search, label: "正在检索临床指南…" },
  { icon: ClipboardCheck, label: "正在生成评估建议…" },
  { icon: Pill, label: "正在整合五大处方…" },
];

/**
 * §6 五大处方 — 生成中可视化
 * 旋转加载 + 进度条 + 多阶段文案
 * 默认 1.5s 切换到 preview
 */
export function GeneratingOverlay({ onDone, durationMs = 6000 }: GeneratingOverlayProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const [progress, setProgress] = useState(0);
  const [stageIdx, setStageIdx] = useState(0);

  useEffect(() => {
    const startTime = Date.now();
    const tick = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const p = Math.min(100, (elapsed / durationMs) * 100);
      setProgress(p);
      setStageIdx(Math.min(STAGES.length - 1, Math.floor((p / 100) * STAGES.length)));
      if (elapsed >= durationMs) {
        clearInterval(tick);
        setProgress(100);
        setStageIdx(STAGES.length - 1);
        setTimeout(() => onDone?.(), 200);
      }
    }, 250);
    return () => clearInterval(tick);
  }, [durationMs, onDone]);

  const StageIcon = STAGES[stageIdx].icon;
  const stageLabel = STAGES[stageIdx].label;

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-col items-center justify-center gap-4 py-10 text-center"
    >
      <Loader2
        className={cn("size-10 animate-spin text-primary", seniorMode && "size-12")}
        aria-hidden
      />
      <div className={cn("font-medium", seniorMode ? "text-lg" : "text-base")}>
        正在为您生成五大处方
      </div>
      <div className="text-sm text-muted-foreground flex items-center gap-1.5">
        <StageIcon className="size-3.5" />
        {stageLabel}
      </div>
      <Progress value={progress} className="w-full max-w-xs" />
      <div className="text-xs text-muted-foreground tabular-nums">
        {Math.round(progress)}%
      </div>
    </div>
  );
}
