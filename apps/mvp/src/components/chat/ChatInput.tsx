"use client";

import { useState } from "react";
import {
  BookOpen,
  ClipboardCheck,
  FileSearch,
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

interface ChatInputProps {
  onSend?: (text: string) => void;
  isGenerating?: boolean;
  onStop?: () => void;
}

/**
 * §3.4 输入框
 * 布局：标签区 → 多行文本框（上方）→ 功能按钮组（底行）
 * 功能按钮：上传文件/技能/五大处方/老年综合评估/用药审查/查看健康画像/语音/发送/停止
 * Enter 发送 / Shift+Enter 换行 / 长度限制
 * 五大处方/CGA/用药审查/健康画像点击后加载到聊天框中执行（中间栏）
 */
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
    if (!trimmed || isGenerating) return;
    onSend?.(trimmed);
    setText("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // 自动增高 textarea
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value.slice(0, INPUT_LIMITS.maxMessageLength));
    const ta = e.target;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
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
        <div className="rounded-xl border border-border bg-muted/50 focus-within:ring-2 focus-within:ring-ring/40 transition-shadow">
          <textarea
            value={text}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={2}
            className={cn(
              "w-full resize-none bg-transparent border-0 outline-none px-3 py-2 text-base leading-relaxed placeholder:text-muted-foreground max-h-[200px]",
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
                  <Square className="size-4" />
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
            ) : (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      variant="ghost"
                      size="icon"
                      className="btn-icon"
                      onClick={() => toast.show("语音输入功能开发中，敬请期待")}
                      aria-label="语音输入"
                    />
                  }
                >
                  <Mic className="size-4" />
                </TooltipTrigger>
                <TooltipContent>语音输入</TooltipContent>
              </Tooltip>
            )}
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
