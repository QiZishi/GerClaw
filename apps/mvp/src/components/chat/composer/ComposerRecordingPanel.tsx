"use client";

import { Check, X } from "lucide-react";

import { cn } from "@/lib/utils";

interface ComposerRecordingPanelProps {
  audioLevel: number;
  duration: string;
  seniorMode: boolean;
  onCancel: () => void;
  onFinish: () => void;
}

export function ComposerRecordingPanel({
  audioLevel,
  duration,
  seniorMode,
  onCancel,
  onFinish,
}: ComposerRecordingPanelProps) {
  return (
    <div className="border-t border-border bg-background px-4 py-3">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-center gap-3 rounded-xl bg-muted/70 px-3 py-3">
          <RecordingButton label="取消录音" seniorMode={seniorMode} onClick={onCancel}>
            <X className={seniorMode ? "size-6" : "size-5"} aria-hidden />
          </RecordingButton>
          <WaveformBars audioLevel={audioLevel} />
          <span
            className={cn(
              "min-w-12 shrink-0 text-center font-medium tabular-nums text-foreground",
              seniorMode ? "text-xl" : "text-lg",
            )}
          >
            {duration}
          </span>
          <RecordingButton label="停止录音并转写" seniorMode={seniorMode} primary onClick={onFinish}>
            <Check className={seniorMode ? "size-6" : "size-5"} strokeWidth={3} aria-hidden />
          </RecordingButton>
        </div>
        <p className={cn("mt-2 text-center text-muted-foreground", seniorMode ? "text-base" : "text-xs")}>
          点击停止后开始识别
        </p>
      </div>
    </div>
  );
}

function RecordingButton({
  label,
  seniorMode,
  primary = false,
  onClick,
  children,
}: {
  label: string;
  seniorMode: boolean;
  primary?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full transition-colors",
        seniorMode ? "size-14" : "size-11",
        primary
          ? "bg-primary text-primary-foreground hover:bg-primary/90"
          : "bg-secondary text-secondary-foreground hover:bg-accent",
      )}
      aria-label={label}
      title={label}
    >
      {children}
    </button>
  );
}

function WaveformBars({ audioLevel }: { audioLevel: number }) {
  const barCount = 28;
  return (
    <div className="flex flex-1 items-center justify-center gap-[3px] overflow-hidden px-4" aria-hidden>
      {Array.from({ length: barCount }).map((_, index) => {
        const centerDistance = Math.abs(index - barCount / 2) / (barCount / 2);
        const baseHeight = 4 + (1 - centerDistance) * 8;
        const height = Math.min(baseHeight * (0.4 + audioLevel * 1.8), 28);
        return (
          <div
            key={index}
            className={cn(
              "h-7 w-[3px] origin-center rounded-full transition-[transform,background-color] duration-100 motion-reduce:transition-none",
              audioLevel > 0.05 ? "bg-foreground" : "bg-border",
            )}
            style={{ transform: `scaleY(${Math.max(height / 28, 0.06)})` }}
          />
        );
      })}
    </div>
  );
}
