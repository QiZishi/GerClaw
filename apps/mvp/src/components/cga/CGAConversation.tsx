"use client";

import { useState, useEffect, useCallback } from "react";
import { ChevronLeft, ChevronRight, Check, Volume2, VolumeX, Mic, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import { useAudioPlayer } from "@/hooks/useAudioPlayer";
import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { recognizeAudio } from "@/services/voice/asr";
import { toast } from "@/components/ui/toast";
import type { Scale, ScaleResult, ScaleOption } from "@/types";

interface CGAConversationProps {
  scale: Scale;
  onComplete?: (result: ScaleResult) => void;
  onExit?: () => void;
}

const POSITIVE_KEYWORDS = ["是", "是的", "对", "有", "嗯", "好", "没错", "正确", "对的", "嗯对", "有的"];
const NEGATIVE_KEYWORDS = ["否", "不是", "没有", "不", "无", "不对", "错", "不是的", "没", "木有"];
const NUMBER_MAP: Record<string, number> = {
  "1": 1, "一": 1, "第一个": 1, "第一": 1,
  "2": 2, "二": 2, "第二个": 2, "第二": 2,
  "3": 3, "三": 3, "第三个": 3, "第三": 3,
  "4": 4, "四": 4, "第四个": 4, "第四": 4,
  "5": 5, "五": 5, "第五个": 5, "第五": 5,
  "6": 6, "六": 6, "第六个": 6, "第六": 6,
  "7": 7, "七": 7, "第七个": 7, "第七": 7,
  "8": 8, "八": 8, "第八个": 8, "第八": 8,
};

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function WaveformBars({ audioLevel, recordingDuration, seniorMode }: { audioLevel: number; recordingDuration: number; seniorMode: boolean }) {
  const barCount = seniorMode ? 20 : 28;
  return (
    <div className="flex items-center justify-center gap-[3px] flex-1 px-4 overflow-hidden">
      {Array.from({ length: barCount }).map((_, i) => {
        const centerDist = Math.abs(i - barCount / 2) / (barCount / 2);
        const baseHeight = 4 + (1 - centerDist) * (seniorMode ? 10 : 8);
        const levelMultiplier = 0.4 + audioLevel * 1.8;
        const height = Math.min(baseHeight * levelMultiplier, seniorMode ? 36 : 28);
        const isActive = audioLevel > 0.05 || (i % 3 === 0 && recordingDuration % 2 === 0);
        return (
          <div
            key={i}
            className={cn(
              "w-[3px] rounded-full transition-all duration-100",
              isActive ? "bg-gray-800 dark:bg-gray-200" : "bg-gray-300 dark:bg-gray-600"
            )}
            style={{ height: `${height}px` }}
          />
        );
      })}
    </div>
  );
}

function matchAnswerByVoice(text: string, options: ScaleOption[]): ScaleOption | null {
  const normalized = text.trim().replace(/[。，！？\s]/g, "");

  for (const keyword of POSITIVE_KEYWORDS) {
    if (normalized.includes(keyword)) {
      const yesOpt = options.find((o) => {
        const label = o.label.replace(/[。，！？\s]/g, "");
        return label.includes("是") || label === "是" || o.value === 1 || label.includes("有");
      });
      if (yesOpt) return yesOpt;
      if (options.length >= 2) return options[0];
    }
  }

  for (const keyword of NEGATIVE_KEYWORDS) {
    if (normalized.includes(keyword) && !normalized.includes("不是没有") && !normalized.includes("不是不")) {
      const noOpt = options.find((o) => {
        const label = o.label.replace(/[。，！？\s]/g, "");
        return label.includes("否") || label === "否" || label === "不是" || o.value === 0 || label.includes("没有") || label.includes("无");
      });
      if (noOpt) return noOpt;
      if (options.length >= 2) return options[options.length - 1];
    }
  }

  for (const [numStr, numVal] of Object.entries(NUMBER_MAP)) {
    if (normalized.includes(numStr) && numVal <= options.length) {
      const idx = numVal - 1;
      if (idx >= 0 && idx < options.length) return options[idx];
    }
  }

  for (const opt of options) {
    const label = opt.label.replace(/[。，！？\s]/g, "");
    if (label && (normalized.includes(label) || label.includes(normalized))) {
      return opt;
    }
  }

  for (const opt of options) {
    if (opt.description) {
      const desc = opt.description.replace(/[。，！？\s]/g, "");
      if (desc && (normalized.includes(desc) || desc.includes(normalized))) {
        return opt;
      }
    }
  }

  return null;
}

export function CGAConversation({ scale, onComplete, onExit }: CGAConversationProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const [idx, setIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<string, number | string>>({});
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [hasSpokenCompletion, setHasSpokenCompletion] = useState(false);

  const { isPlaying, isLoading: ttsLoading, play, stop } = useAudioPlayer();
  const {
    isRecording,
    recordingDuration,
    audioLevel,
    startRecording,
    stopRecording,
    cancelRecording,
  } = useAudioRecorder();

  const total = scale.questions.length;
  const current = scale.questions[idx];
  const progress = ((idx + 1) / total) * 100;
  const isLast = idx === total - 1;
  const answered = current ? answers[current.id] !== undefined : false;

  const speakQuestion = useCallback((questionIndex: number) => {
    const q = scale.questions[questionIndex];
    if (!q) return;
    let text = `第${questionIndex + 1}题：${q.text}。`;
    if (q.options && q.options.length > 0) {
      text += "选项：";
      q.options.forEach((opt, i) => {
        text += `${i + 1}、${opt.label}。`;
      });
    }
    play(text);
  }, [scale.questions, play]);

  useEffect(() => {
    if (seniorMode && current) {
      const timer = setTimeout(() => {
        speakQuestion(idx);
      }, 300);
      return () => clearTimeout(timer);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx, seniorMode, current?.id, speakQuestion]);

  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  const handleSelect = (value: number | string) => {
    if (!current) return;
    setAnswers((a) => ({ ...a, [current.id]: value }));
    stop();
  };

  const handlePrev = () => {
    stop();
    setIdx((i) => Math.max(0, i - 1));
  };

  const handleNext = () => {
    stop();
    if (isLast) {
      handleSubmit();
    } else {
      setIdx((i) => Math.min(total - 1, i + 1));
    }
  };

  const handleSubmit = () => {
    stop();
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
    if (seniorMode && !hasSpokenCompletion) {
      setHasSpokenCompletion(true);
      play("评估已完成，请在右侧查看结果。");
    }
    onComplete?.(result);
  };

  const handleMicStart = async () => {
    if (isTranscribing || isRecording) return;
    stop();
    try {
      await startRecording();
    } catch (err) {
      const message = err instanceof Error ? err.message : "无法启动录音";
      toast.show(message);
    }
  };

  const handleRecordingCancel = () => {
    try {
      cancelRecording();
    } catch {
      toast.show("取消录音失败");
    }
  };

  const handleRecordingFinish = async () => {
    try {
      const blob = await stopRecording();
      setIsTranscribing(true);
      try {
        const recognizedText = await recognizeAudio(blob);
        if (recognizedText && current?.options) {
          const matched = matchAnswerByVoice(recognizedText, current.options);
          if (matched) {
            setAnswers((a) => ({ ...a, [current.id]: matched.value }));
            toast.show(`已选择：${matched.label}`);
            setTimeout(() => {
              if (!isLast) {
                setIdx((i) => Math.min(total - 1, i + 1));
              }
            }, 800);
          } else {
            toast.show(`识别结果："${recognizedText}"，请手动选择选项`);
          }
        } else if (recognizedText) {
          toast.show(`识别结果："${recognizedText}"，请手动选择`);
        }
      } catch {
        toast.show("语音识别失败，请重试或手动选择");
      } finally {
        setIsTranscribing(false);
      }
    } catch {
      toast.show("录音失败，请重试");
      setIsTranscribing(false);
    }
  };

  if (!current) {
    return <div className="text-sm text-muted-foreground">该量表无题目</div>;
  }

  const btnSize = seniorMode ? "h-12 px-5 text-base" : "h-9 px-3 text-sm";
  const iconBtnSize = seniorMode ? "size-12" : "size-10";

  if (isRecording) {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className={cn("font-medium truncate", seniorMode ? "text-base" : "text-sm")}>
              {scale.fullName}
            </div>
            <div className="text-[11px] text-muted-foreground">
              第 {idx + 1} / {total} 题 — 语音答题中
            </div>
          </div>
        </div>
        <Progress value={progress} />
        <div className={cn(
          "rounded-xl bg-muted/70",
          seniorMode ? "px-4 py-5" : "px-3 py-4"
        )}>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleRecordingCancel}
              className={cn(
                "flex items-center justify-center shrink-0 rounded-full bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors",
                seniorMode ? "size-14" : "size-11"
              )}
              aria-label="取消录音"
            >
              <X className={cn(seniorMode ? "size-6" : "size-5")} />
            </button>

            <WaveformBars audioLevel={audioLevel} recordingDuration={recordingDuration} seniorMode={seniorMode} />

            <span className={cn(
              "shrink-0 tabular-nums font-medium text-gray-700 dark:text-gray-300 min-w-[48px] text-center",
              seniorMode ? "text-xl" : "text-lg"
            )}>
              {formatDuration(recordingDuration)}
            </span>

            <button
              type="button"
              onClick={handleRecordingFinish}
              className={cn(
                "flex items-center justify-center shrink-0 rounded-full transition-colors",
                seniorMode ? "size-14" : "size-11",
                "bg-indigo-600 hover:bg-indigo-700 text-white"
              )}
              aria-label="完成答题"
            >
              <Check className={cn(seniorMode ? "size-6" : "size-5")} strokeWidth={3} />
            </button>
          </div>
          <p className={cn(
            "text-center text-muted-foreground mt-3",
            seniorMode ? "text-base" : "text-sm"
          )}>
            请说出您的答案
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
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

      <div
        className={cn(
          "rounded-lg border border-border bg-card",
          seniorMode ? "p-4" : "p-3"
        )}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1">
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
          <button
            type="button"
            onClick={isPlaying || ttsLoading ? stop : () => speakQuestion(idx)}
            className={cn(
              "flex items-center justify-center shrink-0 rounded-full transition-colors",
              iconBtnSize,
              isPlaying
                ? "bg-primary text-primary-foreground"
                : ttsLoading
                  ? "bg-muted text-muted-foreground"
                  : "bg-muted hover:bg-muted/80 text-foreground"
            )}
            aria-label={isPlaying ? "停止朗读" : "朗读题目"}
          >
            {ttsLoading ? (
              <Loader2 className={cn("animate-spin", seniorMode ? "size-5" : "size-4")} />
            ) : isPlaying ? (
              <VolumeX className={cn(seniorMode ? "size-5" : "size-4")} />
            ) : (
              <Volume2 className={cn(seniorMode ? "size-5" : "size-4")} />
            )}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-1.5">
        {current.options?.map((opt) => {
          const selected = answers[current.id] === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => handleSelect(opt.value)}
              className={cn(
                "flex items-center gap-2 rounded-lg border text-left transition-colors",
                seniorMode ? "px-4 py-3 text-base" : "px-3 py-2 text-sm",
                selected
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border bg-background hover:bg-muted"
              )}
              aria-pressed={selected}
            >
              <span
                className={cn(
                  "flex items-center justify-center rounded-full border font-medium shrink-0",
                  seniorMode ? "size-7 text-sm" : "size-5 text-[10px]",
                  selected
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border text-muted-foreground"
                )}
              >
                {selected ? <Check className={cn(seniorMode ? "size-4" : "size-3")} /> : opt.value}
              </span>
              <span className="flex-1">{opt.label}</span>
              {opt.description && (
                <span className={cn("text-muted-foreground", seniorMode ? "text-sm" : "text-[11px]")}>
                  {opt.description}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex items-center justify-between gap-2 pt-1">
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handlePrev}
            disabled={idx === 0}
            className={cn("gap-1", btnSize)}
          >
            <ChevronLeft className={cn(seniorMode ? "size-5" : "size-3.5")} />
            上一题
          </Button>
          <button
            type="button"
            onClick={handleMicStart}
            disabled={isTranscribing}
            className={cn(
              "flex items-center justify-center gap-2 rounded-full transition-colors font-medium",
              seniorMode ? "h-12 px-5 text-base" : "h-10 px-4 text-sm",
              isTranscribing
                ? "bg-muted text-muted-foreground cursor-not-allowed"
                : "bg-rose-500 hover:bg-rose-600 text-white shadow-md"
            )}
            aria-label="语音答题"
          >
            {isTranscribing ? (
              <>
                <Loader2 className={cn("animate-spin", seniorMode ? "size-5" : "size-4")} />
                识别中
              </>
            ) : (
              <>
                <Mic className={cn(seniorMode ? "size-5" : "size-4")} />
                {seniorMode ? "语音答题" : ""}
              </>
            )}
          </button>
        </div>
        {isLast ? (
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={!answered}
            className={cn("gap-1", btnSize)}
          >
            <Check className={cn(seniorMode ? "size-5" : "size-3.5")} />
            提交
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={handleNext}
            disabled={!answered}
            className={cn("gap-1", btnSize)}
          >
            下一题
            <ChevronRight className={cn(seniorMode ? "size-5" : "size-3.5")} />
          </Button>
        )}
      </div>
    </div>
  );
}
