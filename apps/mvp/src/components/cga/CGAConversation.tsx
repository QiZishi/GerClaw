"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { ChevronLeft, ChevronRight, Check, Volume2, Pause, Mic, Loader2, Square, X, CheckCircle2, RotateCcw, ListTodo, BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { useAudioPlayer } from "@/hooks/useAudioPlayer";
import { recognizeAudio } from "@/services/voice/asr";
import { toast } from "@/components/ui/toast";
import { SuicideRiskAlert } from "@/components/prescription/SuicideRiskAlert";
import type { Scale, ScaleResult, ScaleOption } from "@/types";

interface CGAConversationProps {
  scales: Scale[];
  initialAnswers?: Record<string, number | string>;
  initialIndex?: number;
  onComplete?: (results: ScaleResult[]) => void;
  onContinue?: () => void;
  onGenerateReport?: () => void;
  onExit?: () => void;
  onSaveProgress?: (data: { currentQuestionIndex: number; answers: Record<string, number | string> }) => void;
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
const LETTER_MAP: Record<string, number> = {
  "a": 1, "A": 1, "诶": 1, "欸": 1, "ei": 1, "诶选项": 1, "选项a": 1, "选项A": 1, "选项诶": 1,
  "b": 2, "B": 2, "必": 2, "bi": 2, "选项b": 2, "选项B": 2, "选项必": 2,
  "c": 3, "C": 3, "西": 3, "xi": 3, "选项c": 3, "选项C": 3, "选项西": 3,
  "d": 4, "D": 4, "地": 4, "di": 4, "选项d": 4, "选项D": 4, "选项地": 4,
};

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function WaveformBars({ audioLevel, seniorMode }: { audioLevel: number; seniorMode: boolean }) {
  const barCount = seniorMode ? 20 : 28;
  return (
    <div className="flex items-center justify-center gap-[3px] flex-1 px-4 overflow-hidden">
      {Array.from({ length: barCount }).map((_, i) => {
        const centerDist = Math.abs(i - barCount / 2) / (barCount / 2);
        const baseHeight = 4 + (1 - centerDist) * (seniorMode ? 10 : 8);
        const levelMultiplier = 0.4 + audioLevel * 1.8;
        const height = Math.min(baseHeight * levelMultiplier, seniorMode ? 36 : 28);
        const isActive = audioLevel > 0.05;
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

  for (const [letterStr, numVal] of Object.entries(LETTER_MAP)) {
    if (normalized.includes(letterStr) && numVal <= options.length) {
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

interface FlatQuestion {
  scaleId: string;
  scale: Scale;
  questionIndex: number;
  question: Scale["questions"][0];
}

function flattenQuestions(scales: Scale[]): FlatQuestion[] {
  const result: FlatQuestion[] = [];
  for (const scale of scales) {
    for (let i = 0; i < scale.questions.length; i++) {
      result.push({
        scaleId: scale.id,
        scale,
        questionIndex: i,
        question: scale.questions[i],
      });
    }
  }
  return result;
}

function calculateResults(
  scales: Scale[],
  allQuestions: FlatQuestion[],
  answers: Record<string, number | string>
): ScaleResult[] {
  const results: ScaleResult[] = [];
  for (const scale of scales) {
    const scaleQuestions = allQuestions.filter((q) => q.scaleId === scale.id);
    let totalScore = 0;
    const scaleAnswers: Record<string, number | string> = {};
    for (const { question } of scaleQuestions) {
      const val = answers[question.id];
      scaleAnswers[question.id] = val ?? 0;
      const n = typeof val === "number" ? val : Number(val);
      totalScore += Number.isFinite(n) ? n : 0;
    }
    const maxScore = scale.questions.reduce((s, q) => s + (q.maxValue ?? 0), 0);
    const matched = [...scale.grading.thresholds]
      .sort((a, b) => a.max - b.max)
      .find((t) => totalScore <= t.max);
    results.push({
      scaleId: scale.id,
      scaleName: scale.fullName,
      totalScore,
      maxScore,
      level: matched?.level ?? "未知",
      interpretation: matched?.interpretation ?? "",
      answers: scaleAnswers,
      completedAt: Date.now(),
    });
  }
  return results;
}

export function CGAConversation({
  scales,
  initialAnswers,
  initialIndex,
  onComplete,
  onContinue,
  onGenerateReport,
  onExit,
  onSaveProgress,
}: CGAConversationProps) {
  function getInitialAudioEnabled(): boolean {
    try {
      if (typeof window === 'undefined') return false;
      const stored = localStorage.getItem('cga-audio-enabled');
      return stored === 'true';
    } catch {
      return false;
    }
  }

  const seniorMode = useAppStore((s) => s.seniorMode);
  const [idx, setIdx] = useState(initialIndex ?? 0);
  const [answers, setAnswers] = useState<Record<string, number | string>>(initialAnswers ?? {});
  const [isCompleted, setIsCompleted] = useState(false);
  const [results, setResults] = useState<ScaleResult[]>([]);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [hasSpokenCompletion, setHasSpokenCompletion] = useState(false);
  const [cgaAudioEnabled, setCgaAudioEnabled] = useState(getInitialAudioEnabled);
  const [showSuicideRiskAlert, setShowSuicideRiskAlert] = useState(false);
  const [suicideAlertDismissed, setSuicideAlertDismissed] = useState(false);

  const allQuestions = useMemo(() => flattenQuestions(scales), [scales]);
  const total = allQuestions.length;
  const current = allQuestions[idx];

  const {
    isRecording,
    recordingDuration,
    audioLevel,
    startRecording,
    stopRecording,
    cancelRecording,
  } = useAudioRecorder();
  const {
    isPlaying: isAudioPlaying,
    isPaused: isAudioPaused,
    isLoading: isAudioLoading,
    playSource,
    pause: pauseAudio,
    resume: resumeAudio,
    stop: stopAudio,
  } = useAudioPlayer();

  const progress = total > 0 ? ((idx + 1) / total) * 100 : 0;
  const isLast = idx === total - 1;
  const answered = current ? answers[current.question.id] !== undefined : false;
  const currentScale = current?.scale;
  const currentScaleName = currentScale?.fullName ?? "";

  useEffect(() => {
    if (onSaveProgress && !isCompleted) {
      onSaveProgress({ currentQuestionIndex: idx, answers });
    }
  }, [idx, answers, isCompleted, onSaveProgress]);

  const stopAudioByUser = useCallback(() => {
    stopAudio();
    setCgaAudioEnabled(false);
    try {
      localStorage.setItem("cga-audio-enabled", "false");
    } catch {
    }
  }, [stopAudio]);

  const playAudio = useCallback(() => {
    if (!current) return;
    const audioSrc = `/audio/scales/${current.scaleId}_${current.question.id}.wav`;
    void playSource(audioSrc).catch(() => toast.show("题目朗读失败，请稍后重试"));
  }, [current, playSource]);

  const toggleAudio = useCallback(() => {
    if (isAudioLoading) return;
    if (isAudioPlaying) {
      pauseAudio();
    } else if (isAudioPaused) {
      void resumeAudio().catch(() => toast.show("继续朗读失败，请稍后重试"));
    } else {
      setCgaAudioEnabled(true);
      try {
        localStorage.setItem('cga-audio-enabled', 'true');
      } catch {
      }
      playAudio();
    }
  }, [isAudioLoading, isAudioPlaying, isAudioPaused, pauseAudio, resumeAudio, playAudio]);

  useEffect(() => {
    const timer = setTimeout(() => {
      stopAudio();
      if (cgaAudioEnabled && current && !isCompleted) {
        playAudio();
      }
    }, 100);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx, current?.question.id, isCompleted]);

  useEffect(() => {
    return () => {
      stopAudio();
    };
  }, [stopAudio]);

  const handleSelect = (value: number | string) => {
    if (!current) return;
    setAnswers((a) => ({ ...a, [current.question.id]: value }));

    if (current.question.id === "phq9_9") {
      const numVal = typeof value === "number" ? value : Number(value);
      if (numVal > 0) {
        setShowSuicideRiskAlert(true);
        setSuicideAlertDismissed(false);
      }
    }
  };

  const handlePrev = () => {
    stopAudio();
    setIdx((i) => Math.max(0, i - 1));
  };

  const handleNext = () => {
    stopAudio();
    if (isLast) {
      handleSubmit();
    } else {
      setIdx((i) => Math.min(total - 1, i + 1));
    }
  };

  const handleSubmit = () => {
    stopAudio();
    const calculatedResults = calculateResults(scales, allQuestions, answers);
    setResults(calculatedResults);
    setIsCompleted(true);
    if (seniorMode && !hasSpokenCompletion) {
      setHasSpokenCompletion(true);
    }
    onComplete?.(calculatedResults);
  };

  const handleRestart = () => {
    setAnswers({});
    setIdx(0);
    setIsCompleted(false);
    setResults([]);
    setHasSpokenCompletion(false);
  };

  const handleMicStart = async () => {
    if (isTranscribing || isRecording) return;
    stopAudio();
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
        if (recognizedText && current?.question.options) {
          const matched = matchAnswerByVoice(recognizedText, current.question.options);
          if (matched) {
            setAnswers((a) => ({ ...a, [current.question.id]: matched.value }));
            toast.show(`已选择：${matched.label}`);

            if (current.question.id === "phq9_9" && matched.value > 0) {
              setShowSuicideRiskAlert(true);
              setSuicideAlertDismissed(false);
            }
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

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (isRecording || isTranscribing || isCompleted) return;
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) {
        return;
      }
      if (!current?.question.options) return;
      const num = parseInt(e.key, 10);
      if (num >= 1 && num <= 9) {
        const optIdx = num - 1;
        if (optIdx < current.question.options.length) {
          handleSelect(current.question.options[optIdx].value);
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, isRecording, isTranscribing, isCompleted]);

  const btnSize = seniorMode ? "h-12 px-5 text-base" : "h-9 px-3 text-sm";
  const iconBtnSize = seniorMode ? "size-12" : "size-10";

  if (isCompleted) {
    const completedScaleNames = results.map((r) => r.scaleName);
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <div className="flex justify-center mb-6">
          <div className="flex items-center justify-center size-20 rounded-full bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400">
            <CheckCircle2 className={cn(seniorMode ? "size-12" : "size-10")} strokeWidth={2} />
          </div>
        </div>
        <h2 className={cn("font-semibold mb-3", seniorMode ? "text-2xl" : "text-xl")}>
          作答完毕
        </h2>
        <p className={cn("text-muted-foreground mb-8 max-w-md", seniorMode ? "text-lg" : "text-base")}>
          {completedScaleNames.join("、")}已作答完成
        </p>
        <div className="grid grid-cols-3 gap-3 w-full max-w-2xl">
          <Button
            variant="secondary"
            onClick={handleRestart}
            className={cn("flex flex-col items-center gap-2 h-auto py-4", seniorMode ? "text-base min-h-[72px]" : "text-sm")}
          >
            <RotateCcw className={cn(seniorMode ? "size-6" : "size-5")} />
            重新评估
          </Button>
          <Button
            variant="secondary"
            onClick={onContinue}
            className={cn("flex flex-col items-center gap-2 h-auto py-4", seniorMode ? "text-base min-h-[72px]" : "text-sm")}
          >
            <ListTodo className={cn(seniorMode ? "size-6" : "size-5")} />
            继续作答其他量表
          </Button>
          <Button
            onClick={onGenerateReport}
            className={cn("flex flex-col items-center gap-2 h-auto py-4", seniorMode ? "text-base min-h-[72px]" : "text-sm")}
          >
            <BarChart3 className={cn(seniorMode ? "size-6" : "size-5")} />
            查看评估报告
          </Button>
        </div>
      </div>
    );
  }

  if (!current) {
    return <div className="text-sm text-muted-foreground">该量表无题目</div>;
  }

  if (isRecording) {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className={cn("font-medium truncate", seniorMode ? "text-base" : "text-sm")}>
              {currentScaleName}
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

            <WaveformBars audioLevel={audioLevel} seniorMode={seniorMode} />

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
      {showSuicideRiskAlert && !suicideAlertDismissed && (
        <SuicideRiskAlert onDismiss={() => setSuicideAlertDismissed(true)} />
      )}
      
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className={cn("font-medium truncate", seniorMode ? "text-base" : "text-sm")}>
            {currentScaleName}
          </div>
          <div className="text-[11px] text-muted-foreground">
            第 {idx + 1} / {total} 题
          </div>
        </div>
        <div className="flex items-center gap-2">
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
              {current.question.required && <span className="text-destructive ml-1">*</span>}
            </div>
            <div
              className={cn(
                "font-medium leading-relaxed",
                seniorMode ? "text-lg" : "text-sm"
              )}
            >
              {current.question.text}
            </div>
            {current.question.hint && (
              <div className="mt-1.5 text-[11px] text-amber-700 dark:text-amber-300">
                提示：{current.question.hint}
              </div>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1" role="group" aria-label="题目朗读控制">
            <button
              type="button"
              onClick={isAudioLoading ? stopAudioByUser : toggleAudio}
              className={cn(
                "flex items-center justify-center gap-1.5 shrink-0 rounded-full transition-colors",
                seniorMode ? "h-12 px-4 text-base" : iconBtnSize,
                isAudioPlaying
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted hover:bg-muted/80 text-foreground"
              )}
              aria-label={isAudioLoading ? "取消朗读准备" : isAudioPlaying ? "暂停朗读" : isAudioPaused ? "继续朗读" : "朗读题目"}
              aria-busy={isAudioLoading}
            >
              {isAudioPlaying ? (
                <Pause className={cn(seniorMode ? "size-5" : "size-4")} />
              ) : (
                <Volume2 className={cn(seniorMode ? "size-5" : "size-4")} />
              )}
              {seniorMode && <span>{isAudioLoading ? "准备中，点此取消" : isAudioPlaying ? "暂停" : isAudioPaused ? "继续" : "朗读"}</span>}
            </button>
            {(isAudioPlaying || isAudioPaused) && (
              <button
                type="button"
                onClick={stopAudioByUser}
                className={cn(
                  "flex items-center justify-center gap-1.5 rounded-full bg-muted hover:bg-muted/80",
                  seniorMode ? "h-12 px-4 text-base" : iconBtnSize
                )}
                aria-label="停止朗读"
              >
                <Square className={cn(seniorMode ? "size-5" : "size-4")} />
                {seniorMode && <span>停止</span>}
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-1.5">
        {current.question.options?.map((opt) => {
          const selected = answers[current.question.id] === opt.value;
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
