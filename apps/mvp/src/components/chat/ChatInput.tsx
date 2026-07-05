"use client";

import { useState, useRef } from "react";
import {
  BookOpen,
  Check,
  ClipboardCheck,
  FileSearch,
  Loader2,
  Mic,
  Paperclip,
  Pill,
  SendHorizonal,
  UserRound,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAppStore } from "@/stores/appStore";
import { INPUT_LIMITS, MEDICAL_DISCLAIMER } from "@/lib/constants";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { recognizeAudio } from "@/services/voice/asr";

interface ChatInputProps {
  onSend?: (text: string) => void;
  isGenerating?: boolean;
  onStop?: () => void;
}

function WaveformBars({ audioLevel, recordingDuration }: { audioLevel: number; recordingDuration: number }) {
  const barCount = 28;
  return (
    <div className="flex items-center justify-center gap-[3px] flex-1 px-4 overflow-hidden">
      {Array.from({ length: barCount }).map((_, i) => {
        const centerDist = Math.abs(i - barCount / 2) / (barCount / 2);
        const baseHeight = 4 + (1 - centerDist) * 8;
        const levelMultiplier = 0.4 + audioLevel * 1.8;
        const height = Math.min(baseHeight * levelMultiplier, 28);
        const isActive = audioLevel > 0.05 || (i % 3 === 0 && recordingDuration % 2 === 0);
        return (
          <div
            key={i}
            className={cn(
              "w-[3px] rounded-full transition-all duration-100",
              isActive ? "bg-gray-800 dark:bg-gray-200" : "bg-gray-300 dark:bg-gray-600"
            )}
            style={{
              height: `${height}px`,
            }}
          />
        );
      })}
    </div>
  );
}

function FunctionButtonGroup({
  disabled,
  role,
  onShowToast,
  onSetMainView,
  onSetChatAction,
}: {
  disabled: boolean;
  role: "patient" | "doctor" | "visitor";
  onShowToast: (msg: string) => void;
  onSetMainView: (view: "skills" | "chat") => void;
  onSetChatAction: (action: "prescription" | "cga" | "drug-review" | "health-profile" | "none") => void;
}) {
  return (
    <div className="flex items-center gap-0.5 flex-wrap">
      <Tooltip>
        <TooltipTrigger
          render={
            <Button
              variant="ghost"
              size="icon"
              className="btn-icon"
              onClick={() => onShowToast("文件上传功能开发中，敬请期待")}
              aria-label="上传文件或图片"
              disabled={disabled}
            />
          }
        >
          <Paperclip className="size-4" />
        </TooltipTrigger>
        <TooltipContent>上传文件或图片</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger
          render={
            <Button
              variant="ghost"
              size="icon"
              className="btn-icon"
              onClick={() => onSetMainView("skills")}
              aria-label="技能"
              disabled={disabled}
            />
          }
        >
          <BookOpen className="size-4" />
        </TooltipTrigger>
        <TooltipContent>技能</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger
          render={
            <Button
              variant="ghost"
              size="icon"
              className="btn-icon"
              onClick={() => onSetChatAction("prescription")}
              aria-label="五大处方生成"
              disabled={disabled}
            />
          }
        >
          <Pill className="size-4" />
        </TooltipTrigger>
        <TooltipContent>五大处方生成</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger
          render={
            <Button
              variant="ghost"
              size="icon"
              className="btn-icon"
              onClick={() => onSetChatAction("cga")}
              aria-label="老年综合评估"
              disabled={disabled}
            />
          }
        >
          <ClipboardCheck className="size-4" />
        </TooltipTrigger>
        <TooltipContent>老年综合评估</TooltipContent>
      </Tooltip>
      {role === "doctor" && (
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant="ghost"
                size="icon"
                className="btn-icon"
                onClick={() => onSetChatAction("drug-review")}
                aria-label="用药审查"
                disabled={disabled}
              />
            }
          >
            <FileSearch className="size-4" />
          </TooltipTrigger>
          <TooltipContent>用药审查</TooltipContent>
        </Tooltip>
      )}
      <Tooltip>
        <TooltipTrigger
          render={
            <Button
              variant="ghost"
              size="icon"
              className="btn-icon"
              onClick={() => onSetChatAction("health-profile")}
              aria-label={role === "doctor" ? "查看健康画像" : "我的健康画像"}
              disabled={disabled}
            />
          }
        >
          <UserRound className="size-4" />
        </TooltipTrigger>
        <TooltipContent>
          {role === "doctor" ? "查看健康画像" : "我的健康画像"}
        </TooltipContent>
      </Tooltip>
    </div>
  );
}

export function ChatInput({ onSend, isGenerating, onStop }: ChatInputProps) {
  const role = useAppStore((s) => s.role);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const loadedSkillIds = useAppStore((s) => s.loadedSkillIds);
  const uploadedFileIds = useAppStore((s) => s.uploadedFileIds);
  const removeLoadedSkill = useAppStore((s) => s.removeLoadedSkill);
  const removeUploadedFile = useAppStore((s) => s.removeUploadedFile);
  const setMainView = useAppStore((s) => s.setMainView);
  const setChatAction = useAppStore((s) => s.setChatAction);

  const [text, setText] = useState("");
  const [isTranscribing, setIsTranscribing] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const {
    isRecording,
    recordingDuration,
    audioLevel,
    startRecording,
    stopRecording,
    cancelRecording,
  } = useAudioRecorder();

  const placeholder =
    role === "doctor"
      ? seniorMode
        ? "请描述患者病情或需要评估的内容…"
        : "请输入患者病情或评估需求…"
      : seniorMode
        ? "请描述您的不适或健康问题，例如：我最近血压偏高…"
        : "描述您的健康问题…";

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || isGenerating || isTranscribing) return;
    onSend?.(trimmed);
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !isRecording && !isTranscribing) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value.slice(0, INPUT_LIMITS.maxMessageLength));
    const ta = e.target;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  };

  const formatDuration = (seconds: number): string => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  const handleMicStart = async () => {
    if (isTranscribing || isGenerating) return;
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
        if (recognizedText) {
          setText((prev) => {
            const newText = prev ? prev + " " + recognizedText : recognizedText;
            return newText.slice(0, INPUT_LIMITS.maxMessageLength);
          });
          setTimeout(() => {
            if (textareaRef.current) {
              textareaRef.current.style.height = "auto";
              textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
              textareaRef.current.focus();
            }
          }, 50);
        }
      } catch {
        toast.show("语音识别失败，请重试");
      } finally {
        setIsTranscribing(false);
      }
    } catch {
      toast.show("录音失败，请重试");
    }
  };

  if (isRecording) {
    return (
      <div className="border-t border-border bg-background px-4 py-3">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-center gap-3 rounded-xl bg-muted/70 px-3 py-3">
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

            <WaveformBars audioLevel={audioLevel} recordingDuration={recordingDuration} />

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
              aria-label="完成录音"
            >
              <Check className={cn(seniorMode ? "size-6" : "size-5")} strokeWidth={3} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="border-t border-border bg-background px-4 py-3">
      <div className="max-w-3xl mx-auto">
        {(loadedSkillIds.length > 0 || uploadedFileIds.length > 0) && (
          <div className="flex flex-wrap gap-2 mb-2">
            {loadedSkillIds.map((id) => (
              <span
                key={id}
                className="inline-flex items-center gap-1 rounded-full bg-primary/10 text-primary text-xs px-2 py-1"
              >
                <BookOpen className="size-3" />
                {id}
                <button
                  type="button"
                  onClick={() => removeLoadedSkill(id)}
                  className="hover:bg-primary/20 rounded-full p-0.5"
                  aria-label="移除技能"
                >
                  <X className="size-3" />
                </button>
              </span>
            ))}
            {uploadedFileIds.map((id) => (
              <span
                key={id}
                className="inline-flex items-center gap-1 rounded-full bg-muted text-foreground text-xs px-2 py-1"
              >
                <Paperclip className="size-3" />
                {id}
                <button
                  type="button"
                  onClick={() => removeUploadedFile(id)}
                  className="hover:bg-muted-foreground/20 rounded-full p-0.5"
                  aria-label="移除文件"
                >
                  <X className="size-3" />
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="rounded-xl border border-border bg-muted/50 focus-within:ring-2 focus-within:ring-ring/40 transition-shadow">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder={isTranscribing ? (seniorMode ? "正在识别语音…" : "识别中…") : placeholder}
            rows={2}
            disabled={isTranscribing}
            className={cn(
              "w-full resize-none bg-transparent border-0 outline-none px-3 py-2 text-base leading-relaxed placeholder:text-muted-foreground max-h-[200px] disabled:opacity-60",
              seniorMode && "text-lg"
            )}
          />

          <div className="flex items-center justify-between gap-1 px-2 py-1.5 border-t border-border/60">
            <FunctionButtonGroup
              disabled={isTranscribing}
              role={role}
              onShowToast={(msg) => toast.show(msg)}
              onSetMainView={setMainView}
              onSetChatAction={setChatAction}
            />

            <div className="flex items-center">
              {isGenerating ? (
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        variant="destructive"
                        size="icon"
                        className="btn-icon"
                        onClick={onStop}
                        aria-label="停止生成"
                      />
                    }
                  >
                    <span className="size-2.5 bg-current rounded-sm" />
                  </TooltipTrigger>
                  <TooltipContent>停止生成</TooltipContent>
                </Tooltip>
              ) : text.trim() ? (
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        variant="default"
                        size="icon"
                        className="btn-icon"
                        onClick={handleSend}
                        aria-label="发送"
                      />
                    }
                  >
                    <SendHorizonal className="size-4" />
                  </TooltipTrigger>
                  <TooltipContent>发送</TooltipContent>
                </Tooltip>
              ) : isTranscribing ? (
                <div className="flex items-center gap-2 px-2">
                  <Loader2 className={cn("animate-spin text-primary", seniorMode ? "size-5" : "size-4")} />
                  <span className={cn("text-primary", seniorMode ? "text-base" : "text-sm")}>
                    {seniorMode ? "正在识别…" : "识别中…"}
                  </span>
                </div>
              ) : (
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        variant="ghost"
                        size="icon"
                        className={cn("btn-icon", seniorMode && "size-12")}
                        onClick={handleMicStart}
                        aria-label="语音输入"
                      />
                    }
                  >
                    <Mic className={cn(seniorMode ? "size-5" : "size-4")} />
                  </TooltipTrigger>
                  <TooltipContent>语音输入</TooltipContent>
                </Tooltip>
              )}
            </div>
          </div>
        </div>

        <div className="mt-1.5 text-xs text-muted-foreground">
          {MEDICAL_DISCLAIMER}
        </div>
      </div>
    </div>
  );
}
