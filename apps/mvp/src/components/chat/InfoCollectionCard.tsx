"use client";

import { useState, useRef, useCallback } from "react";
import { CheckCircle2, Mic, Send, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/stores/appStore";
import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { recognizeAudio } from "@/services/voice/asr";
import { toast } from "@/components/ui/toast";
import type { QuestionCardData } from "@/types";

interface InfoField {
  key: string;
  label: string;
  value?: string | number;
  filled: boolean;
}

interface InfoCollectionCardProps {
  fields: InfoField[];
  compact?: boolean;
}

export function InfoCollectionCard({ fields, compact = false }: InfoCollectionCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border/50 bg-card",
        compact ? "p-2" : "p-3"
      )}
    >
      <h4
        className={cn(
          "font-medium text-foreground mb-2",
          compact ? "text-sm" : "text-base"
        )}
      >
        已收集信息
      </h4>
      <div
        className={cn(
          "grid gap-2",
          "grid-cols-2 sm:grid-cols-3 md:grid-cols-4"
        )}
      >
        {fields.map((field) => (
          <div
            key={field.key}
            className={cn(
              "flex items-start gap-1.5",
              compact ? "text-sm" : "text-base"
            )}
          >
            {field.filled ? (
              <CheckCircle2
                className={cn(
                  "text-green-500 shrink-0 mt-0.5",
                  compact ? "size-4" : "size-5"
                )}
              />
            ) : (
              <div
                className={cn(
                  "rounded-full bg-muted shrink-0 mt-0.5",
                  compact ? "size-4" : "size-5"
                )}
              />
            )}
            <div className="min-w-0">
              <span
                className={cn(
                  "text-muted-foreground",
                  compact ? "text-xs" : "text-sm"
                )}
              >
                {field.label}
              </span>
              <p
                className={cn(
                  "font-medium truncate",
                  field.filled ? "text-foreground" : "text-muted-foreground",
                  compact ? "text-sm" : "text-base"
                )}
              >
                {field.filled && field.value !== undefined
                  ? String(field.value)
                  : "待补充"}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

interface QuestionCardProps {
  data: QuestionCardData;
  onSubmit: (answers: Record<string, string>) => void;
  disabled?: boolean;
}

export function QuestionCard({ data, onSubmit, disabled = false }: QuestionCardProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const [answers, setAnswers] = useState<Record<string, string>>(data.answers || {});
  const [activeQuestionId, setActiveQuestionId] = useState<string | null>(null);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const textareaRefs = useRef<Record<string, HTMLTextAreaElement | null>>({});

  const {
    isRecording,
    startRecording,
    stopRecording,
  } = useAudioRecorder();

  const handleInputChange = (questionId: string, value: string) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
  };

  const handleVoiceInput = async (questionId: string) => {
    if (isRecording) {
      try {
        const blob = await stopRecording();
        setIsTranscribing(true);
        try {
          const recognizedText = await recognizeAudio(blob);
          if (recognizedText) {
            setAnswers((prev) => {
              const existing = prev[questionId] || "";
              const newText = existing ? existing + " " + recognizedText : recognizedText;
              return { ...prev, [questionId]: newText };
            });
            toast.show("语音识别完成");
          }
        } catch {
          toast.show("语音识别失败，请重试");
        } finally {
          setIsTranscribing(false);
        }
      } catch {
        setIsTranscribing(false);
      }
    } else {
      setActiveQuestionId(questionId);
      await startRecording();
    }
  };

  const handleSubmit = useCallback(() => {
    if (disabled || data.submitted) return;
    onSubmit(answers);
  }, [answers, disabled, data.submitted, onSubmit]);

  const allFilled = data.questions.every((q) => (answers[q.id] || "").trim().length > 0);
  const anyFilled = data.questions.some((q) => (answers[q.id] || "").trim().length > 0);

  const labelSize = seniorMode ? "text-lg" : "text-base";
  const inputSize = seniorMode ? "text-lg" : "text-sm";
  const btnMinHeight = seniorMode ? "min-h-12" : "min-h-10";

  if (data.submitted) {
    return (
      <div className="rounded-2xl border border-border/60 bg-gradient-to-br from-blue-50/80 to-indigo-50/50 dark:from-blue-950/20 dark:to-indigo-950/10 p-4 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">📋</span>
            <span className={cn("font-semibold text-foreground", labelSize)}>信息补充</span>
            <span className={cn("text-muted-foreground", seniorMode ? "text-base" : "text-sm")}>
              第{data.round}轮/最多{data.maxRounds}轮
            </span>
          </div>
          <CheckCircle2 className="size-5 text-green-500" />
        </div>
        <div className="space-y-3">
          {data.questions.map((q) => {
            const answer = data.answers[q.id] || answers[q.id] || "";
            return (
              <div key={q.id} className="space-y-1">
                <div className={cn("font-medium text-foreground flex items-center gap-2", labelSize)}>
                  <CheckCircle2 className="size-4 text-green-500 shrink-0" />
                  {q.label}
                </div>
                <p className={cn("text-foreground/80 pl-6", seniorMode ? "text-base" : "text-sm")}>
                  {answer}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-border/60 bg-gradient-to-br from-blue-50/80 to-indigo-50/50 dark:from-blue-950/20 dark:to-indigo-950/10 p-4 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-lg">📋</span>
          <span className={cn("font-semibold text-foreground", labelSize)}>信息补充</span>
          <span className={cn("text-muted-foreground bg-muted/60 px-2 py-0.5 rounded-full", seniorMode ? "text-sm" : "text-xs")}>
            第{data.round}轮/最多{data.maxRounds}轮
          </span>
        </div>
      </div>

      <div className="space-y-4">
        {data.questions.map((question, idx) => {
          const value = answers[question.id] || "";
          const isActive = activeQuestionId === question.id && isRecording;
          const isFilled = value.trim().length > 0;
          return (
            <div key={question.id} className="space-y-1.5">
              <label
                className={cn(
                  "font-medium text-foreground flex items-center gap-2",
                  labelSize
                )}
              >
                <span className="inline-flex items-center justify-center size-5 rounded-full bg-primary/10 text-primary text-xs font-semibold shrink-0">
                  {idx + 1}
                </span>
                {question.label}
                {question.required && <span className="text-red-500">*</span>}
                {isFilled && <CheckCircle2 className="size-4 text-green-500 shrink-0" />}
              </label>
              <div className="relative">
                <textarea
                  ref={(el) => { textareaRefs.current[question.id] = el; }}
                  value={value}
                  onChange={(e) => handleInputChange(question.id, e.target.value)}
                  placeholder={question.placeholder || "请输入您的回答..."}
                  disabled={disabled}
                  rows={question.type === "textarea" ? 2 : 1}
                  className={cn(
                    "w-full rounded-xl border border-input bg-background px-3 py-2.5 pr-10",
                    "placeholder:text-muted-foreground/60",
                    "focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary",
                    "resize-none transition-colors",
                    "disabled:opacity-50 disabled:cursor-not-allowed",
                    inputSize
                  )}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey && question.type !== "textarea") {
                      e.preventDefault();
                      if (allFilled) handleSubmit();
                    }
                  }}
                />
                <button
                  type="button"
                  onClick={() => handleVoiceInput(question.id)}
                  disabled={disabled || isTranscribing}
                  className={cn(
                    "absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-lg transition-colors",
                    isActive
                      ? "bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400 animate-pulse"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted",
                    "disabled:opacity-50"
                  )}
                  title={isRecording ? "停止录音" : "语音输入"}
                >
                  {isTranscribing ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Mic className={cn(isActive ? "size-4" : "size-4")} />
                  )}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 flex justify-end">
        <Button
          onClick={handleSubmit}
          disabled={disabled || !anyFilled}
          className={cn(
            "gap-2 rounded-xl",
            btnMinHeight,
            seniorMode ? "text-base px-6" : "text-sm px-4"
          )}
        >
          <Send className="size-4" />
          {allFilled ? "提交" : "提交已填内容"}
        </Button>
      </div>
    </div>
  );
}

interface StageIndicatorProps {
  title: string;
  description?: string;
  active?: boolean;
}

export function StageIndicator({ title, description, active = true }: StageIndicatorProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  return (
    <div className={cn(
      "rounded-xl border border-border/50 bg-card p-3 flex items-center gap-3",
      active && "border-primary/30 bg-primary/5"
    )}>
      <div className={cn(
        "size-8 rounded-full flex items-center justify-center shrink-0",
        active ? "bg-primary text-primary-foreground animate-pulse" : "bg-muted text-muted-foreground"
      )}>
        <Loader2 className={cn("size-4", active && "animate-spin")} />
      </div>
      <div className="min-w-0">
        <p className={cn("font-medium text-foreground", seniorMode ? "text-base" : "text-sm")}>
          {title}
        </p>
        {description && (
          <p className={cn("text-muted-foreground", seniorMode ? "text-sm" : "text-xs")}>
            {description}
          </p>
        )}
      </div>
    </div>
  );
}
