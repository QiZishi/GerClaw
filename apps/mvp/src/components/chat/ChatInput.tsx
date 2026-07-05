"use client";

import { useState, useRef } from "react";
import {
  BookOpen,
  ClipboardCheck,
  FileSearch,
  Loader2,
  Mic,
  Paperclip,
  Pill,
  SendHorizonal,
  Square,
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

  const handleMicClick = async () => {
    if (isRecording) {
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
    } else if (!isTranscribing && !isGenerating) {
      try {
        await startRecording();
      } catch (err) {
        const message = err instanceof Error ? err.message : "无法启动录音";
        toast.show(message);
      }
    }
  };

  const VolumeIndicator = () => {
    const bars = 4;
    return (
      <div className="flex items-center gap-0.5 ml-1">
        {Array.from({ length: bars }).map((_, i) => {
          const threshold = (i + 1) / bars;
          const isActive = audioLevel > threshold * 0.6;
          return (
            <div
              key={i}
              className={cn(
                "w-1 rounded-full transition-all duration-75",
                isActive ? "bg-red-500" : "bg-red-200 dark:bg-red-900/40"
              )}
              style={{
                height: `${6 + i * 3}px`,
              }}
            />
          );
        })}
      </div>
    );
  };

  const renderMicButton = () => {
    if (isGenerating) {
      return (
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
            <Square className="size-4" />
          </TooltipTrigger>
          <TooltipContent>停止生成</TooltipContent>
        </Tooltip>
      );
    }

    if (text.trim()) {
      return (
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
      );
    }

    if (isTranscribing) {
      return (
        <div className="flex items-center gap-2 px-2">
          <Loader2 className={cn("animate-spin text-primary", seniorMode ? "size-5" : "size-4")} />
          <span className={cn("text-primary", seniorMode ? "text-base" : "text-sm")}>
            {seniorMode ? "正在识别…" : "识别中…"}
          </span>
        </div>
      );
    }

    if (isRecording) {
      return (
        <div className="flex items-center">
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="destructive"
                  size="icon"
                  className={cn(
                    "btn-icon animate-pulse",
                    seniorMode && "size-12"
                  )}
                  onClick={handleMicClick}
                  aria-label="停止录音"
                />
              }
            >
              <Square className={cn(seniorMode ? "size-5" : "size-4")} />
            </TooltipTrigger>
            <TooltipContent>停止录音</TooltipContent>
          </Tooltip>
          <span className={cn("ml-2 tabular-nums text-red-500 font-medium", seniorMode ? "text-base" : "text-sm")}>
            {formatDuration(recordingDuration)}
          </span>
          <VolumeIndicator />
          {seniorMode && (
            <span className="ml-2 text-red-500 text-base">正在录音…（再次点击停止）</span>
          )}
        </div>
      );
    }

    return (
      <Tooltip>
        <TooltipTrigger
          render={
            <Button
              variant="ghost"
              size="icon"
              className={cn("btn-icon", seniorMode && "size-12")}
              onClick={handleMicClick}
              aria-label="语音输入"
            />
          }
        >
          <Mic className={cn(seniorMode ? "size-5" : "size-4")} />
        </TooltipTrigger>
        <TooltipContent>语音输入</TooltipContent>
      </Tooltip>
    );
  };

  return (
    <div className="border-t border-border bg-background px-4 py-3">
      <div className="max-w-3xl mx-auto">
        {/* 标签区域 */}
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

        {/* 多行文本框（上方）*/}
        <div className={cn(
          "rounded-xl border border-border bg-muted/50 focus-within:ring-2 focus-within:ring-ring/40 transition-shadow",
          isRecording && "border-red-400 ring-2 ring-red-200 dark:ring-red-900/40"
        )}>
          <textarea
            ref={textareaRef}
            value={text}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder={isRecording ? (seniorMode ? "正在录音…" : "录音中…") : placeholder}
            rows={2}
            disabled={isRecording || isTranscribing}
            className={cn(
              "w-full resize-none bg-transparent border-0 outline-none px-3 py-2 text-base leading-relaxed placeholder:text-muted-foreground max-h-[200px] disabled:opacity-60",
              seniorMode && "text-lg"
            )}
          />

          {/* 底部功能按钮行 */}
          <div className="flex items-center justify-between gap-1 px-2 py-1.5 border-t border-border/60">
            {/* 左侧功能按钮组 */}
            <div className="flex items-center gap-0.5 flex-wrap">
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      variant="ghost"
                      size="icon"
                      className="btn-icon"
                      onClick={() => toast.show("文件上传功能开发中，敬请期待")}
                      aria-label="上传文件或图片"
                      disabled={isRecording || isTranscribing}
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
                      onClick={() => setMainView("skills")}
                      aria-label="技能"
                      disabled={isRecording || isTranscribing}
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
                      onClick={() => setChatAction("prescription")}
                      aria-label="五大处方生成"
                      disabled={isRecording || isTranscribing}
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
                      onClick={() => setChatAction("cga")}
                      aria-label="老年综合评估"
                      disabled={isRecording || isTranscribing}
                    />
                  }
                >
                  <ClipboardCheck className="size-4" />
                </TooltipTrigger>
                <TooltipContent>老年综合评估</TooltipContent>
              </Tooltip>
              {/* 用药审查：仅医生端可见 */}
              {role === "doctor" && (
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        variant="ghost"
                        size="icon"
                        className="btn-icon"
                        onClick={() => setChatAction("drug-review")}
                        aria-label="用药审查"
                        disabled={isRecording || isTranscribing}
                      />
                    }
                  >
                    <FileSearch className="size-4" />
                  </TooltipTrigger>
                  <TooltipContent>用药审查</TooltipContent>
                </Tooltip>
              )}
              {/* 健康画像：医生患者都可见，两端功能差异化 */}
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      variant="ghost"
                      size="icon"
                      className="btn-icon"
                      onClick={() => setChatAction("health-profile")}
                      aria-label={
                        role === "doctor" ? "查看健康画像" : "我的健康画像"
                      }
                      disabled={isRecording || isTranscribing}
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

            {/* 右侧发送/停止/语音 */}
            {renderMicButton()}
          </div>
        </div>

        {/* 医疗免责声明（仅显示，不显示字数统计）*/}
        <div className="mt-1.5 text-xs text-muted-foreground">
          {MEDICAL_DISCLAIMER}
        </div>
      </div>
    </div>
  );
}
