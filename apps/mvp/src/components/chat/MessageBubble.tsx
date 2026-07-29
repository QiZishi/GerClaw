"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Check,
  Copy,
  FileEdit,
  MoreHorizontal,
  RefreshCw,
  Share2,
  Stethoscope,
  ThumbsDown,
  ThumbsUp,
  Trash2,
} from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import { cn } from "@/lib/utils";
import { SimpleStepIndicator } from "./blocks/SimpleStepIndicator";
import { SourceReferences } from "@/components/search/SourceReferences";
import { MEDICAL_DISCLAIMER } from "@/lib/constants";
import type { Message, MessageBlock, RightPanelType } from "@/types";
import { toast } from "@/components/ui/toast";
import { createFeedbackIdempotencyKey, submitFeedback } from "@/services/gerclaw/feedback";
import { MessageBody } from "@/components/chat/message/MessageBody";
import {
  AssistantRunStatus,
  IncompleteAnswerWarning,
} from "@/components/chat/message/MessageStatusNotices";
import { MessageVoiceReadButton } from "@/components/chat/message/MessageVoiceReadButton";

interface MessageBubbleProps {
  message: Message;
  onRegenerate?: (id: string) => void;
  onCopy?: (id: string) => void;
  onShare?: (id: string) => void;
  onDelete?: (id: string) => void;
  onEdit?: (id: string) => void;
  isLastMessage?: boolean;
}

function extractPlainText(blocks: MessageBlock[]): string {
  return blocks
    .filter((b): b is Extract<MessageBlock, { kind: "text" }> => b.kind === "text")
    .map((b) => b.content)
    .join("\n")
    .replace(/[#*`_~\[\]()>|-]/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function MessageBubble({
  message,
  onRegenerate,
  onCopy,
  onShare,
  onDelete,
  onEdit,
  isLastMessage,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  const [appeared, setAppeared] = useState(false);
  const [showFeedbackDialog, setShowFeedbackDialog] = useState(false);
  const [feedbackType, setFeedbackType] = useState<"up" | "down" | null>(null);
  const [feedbackText, setFeedbackText] = useState("");
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const role = useAppStore((s) => s.role);
  const autoTtsPlayback = useAppStore((s) => s.autoTtsPlayback);
  const ttsAvailable = useAppStore((s) => s.ttsAvailable);
  const setRightPanel = useAppStore((s) => s.setRightPanel);
  const setPanelContent = useAppStore((s) => s.setPanelContent);
  const setMessageFeedback = useChatStore((s) => s.setMessageFeedback);
  const updateMessage = useChatStore((s) => s.updateMessage);

  const autoPlayEligible = Boolean(
    message.autoTtsPending &&
    role === "patient" &&
    seniorMode &&
    autoTtsPlayback &&
    ttsAvailable
  );
  const markAutoPlaybackConsumed = useCallback(() => {
    updateMessage(message.id, { autoTtsPending: false });
  }, [message.id, updateMessage]);

  useEffect(() => {
    // 用户在生成结束后关闭自动朗读、离开患者模式或语音服务不可用时，
    // 不保留待播信号，避免随后打开历史消息时突然出声。
    if (message.autoTtsPending && !autoPlayEligible) {
      markAutoPlaybackConsumed();
    }
  }, [autoPlayEligible, markAutoPlaybackConsumed, message.autoTtsPending]);

  const feedback = message.feedback ?? null;

  useEffect(() => {
    const timer = setTimeout(() => setAppeared(true), 10);
    return () => clearTimeout(timer);
  }, []);

  const handleViewReport = (panelType: RightPanelType) => {
    const session = useChatStore
      .getState()
      .sessions.find((item) => item.id === message.sessionId);
    setRightPanel(panelType);
    setPanelContent(
      session?.panelType === panelType ? session.panelContent ?? "" : ""
    );
  };

  const handleCopy = () => {
    const textContent = extractPlainText(message.blocks);
    navigator.clipboard?.writeText(textContent).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast.show("已复制");
    });
    onCopy?.(message.id);
  };

  const handleFeedbackClick = (type: "up" | "down") => {
    if (!message.traceId || feedback || feedbackSubmitting) return;
    setFeedbackType(type);
    setFeedbackText("");
    setShowFeedbackDialog(true);
  };

  const dismissFeedbackDialog = () => {
    setShowFeedbackDialog(false);
    setFeedbackText("");
    setFeedbackType(null);
  };

  const submitMessageFeedback = async () => {
    if (!feedbackType || !message.traceId || feedbackSubmitting) return;
    const idempotencyKey = message.feedbackIdempotencyKey ?? createFeedbackIdempotencyKey();
    const comment = feedbackText.trim();
    updateMessage(message.id, { feedbackIdempotencyKey: idempotencyKey });
    setFeedbackSubmitting(true);
    try {
      await submitFeedback({
        traceId: message.traceId,
        idempotencyKey,
        rating: feedbackType === "up" ? "positive" : "negative",
        ...(comment ? { comment } : {}),
      });
      setMessageFeedback(message.id, feedbackType, comment || undefined);
      toast.show("反馈已提交，感谢您的帮助");
      dismissFeedbackDialog();
    } catch {
      toast.show("反馈暂未提交，请检查网络后重试");
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  const handleEditInDoc = () => {
    const textContent = extractPlainText(message.blocks);
    setRightPanel("doc-editor");
    setPanelContent(textContent);
    onEdit?.(message.id);
  };

  const handleDelete = () => {
    onDelete?.(message.id);
  };

  const handleShare = () => {
    onShare?.(message.id);
  };

  const plainText = extractPlainText(message.blocks);
  const hasInlineDisclaimer = message.blocks.some(
    (block) =>
      block.kind === "text" &&
      (block.content.includes(MEDICAL_DISCLAIMER) || block.content.includes("免责声明"))
  );
  const hasActiveThinking = !isUser && message.blocks.some(
    (b) => b.kind === "thinking" && b.data.status === "thinking"
  );
  const hasEmergencyAlert = !isUser && message.blocks.some(
    (block) => block.kind === "emergency_alert"
  );
  const messageAnimation = cn(
    "transition-[transform,opacity] duration-200 ease-[var(--motion-ease-out)]",
    appeared
      ? "opacity-100 translate-y-0"
      : "opacity-0 translate-y-2 motion-reduce:translate-y-0",
    "motion-reduce:transition-opacity"
  );
  const iconSize = seniorMode ? "size-5" : "size-3.5";
  const btnSize = seniorMode ? "default" : "icon-sm";
  const seniorActionClass = seniorMode ? "min-h-12 gap-1.5 px-3 text-base" : undefined;
  const showRegenerate =
    !isUser &&
    isLastMessage &&
    onRegenerate &&
    (message.status === "done" || message.status === "stopped" || message.status === "error");
  const stoppedAssistant = !isUser && message.status === "stopped";
  const errorAssistant = !isUser && message.status === "error";
  const companionMode = message.workflow === "companion";

  return (
    <div
      data-message-bubble
      className={cn(
        "group flex gap-3 px-4 py-3",
        isUser ? "flex-row-reverse" : "flex-row",
        messageAnimation
      )}
    >
      <Avatar className="mt-0.5 shrink-0" size="default">
        <AvatarFallback
          className={cn(
            isUser
              ? "bg-primary text-primary-foreground"
              : "bg-secondary text-secondary-foreground"
          )}
        >
          {isUser ? (
            <span className="text-xs">我</span>
          ) : (
            <Stethoscope className="size-4" />
          )}
        </AvatarFallback>
      </Avatar>

      <div
        className={cn(
          "flex min-w-0 max-w-[calc(100%-3rem)] flex-col gap-2 sm:max-w-[85%] lg:max-w-[80%]",
          isUser ? "items-end" : "items-start"
        )}
      >
        {!isUser && message.status === "streaming" && (
          <AssistantRunStatus
            startedAt={message.createdAt}
            phase={hasActiveThinking ? "正在分析您的问题" : "正在生成答复"}
            seniorMode={seniorMode}
          />
        )}
        {!isUser && errorAssistant && (
          <IncompleteAnswerWarning seniorMode={seniorMode} companionMode={companionMode} />
        )}
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5 shadow-sm",
            isUser
              ? "bg-primary text-primary-foreground rounded-tr-sm"
              : "bg-card text-foreground rounded-tl-sm border border-border/50"
          )}
        >
          {!isUser && message.steps && message.steps.length > 0 && (
            <SimpleStepIndicator steps={message.steps} />
          )}
          <MessageBody
            message={message}
            seniorMode={seniorMode}
            hasActiveThinking={hasActiveThinking}
            onViewReport={handleViewReport}
          />
        </div>

        {message.hasDisclaimer && !hasInlineDisclaimer && (
          <div className={cn(
            "text-muted-foreground px-2",
            seniorMode ? "text-lg leading-relaxed" : "text-[11px]"
          )}>
            {companionMode
              ? "此模式提供情感支持，不替代医疗咨询、心理治疗或紧急援助。"
              : MEDICAL_DISCLAIMER}
          </div>
        )}

        {!isUser && message.citations && message.citations.length > 0 && message.status === "done" && (
          <div className="px-1 w-full">
            <SourceReferences citations={message.citations} />
          </div>
        )}

        {!hasEmergencyAlert && (message.status === "done" || stoppedAssistant || errorAssistant) && (
          <div className="relative">
            <div
              data-message-actions
              data-html2canvas-ignore
              className={cn(
                "flex items-center gap-0.5 transition-opacity duration-150",
                "rounded-full bg-muted/40 border border-border/40 px-1 py-0.5",
                seniorMode || errorAssistant
                  ? "flex-wrap gap-1 rounded-xl px-2 py-1 opacity-100"
                  : "opacity-0 group-hover:opacity-100 focus-within:opacity-100"
              )}
            >
              {!isUser && message.status === "done" && message.traceId ? (
                <>
                  <Tooltip>
                    <TooltipTrigger
                      render={
                        <Button
                          variant="ghost"
                          size={btnSize}
                          className={cn(seniorActionClass, feedback === 'up' && "text-primary bg-primary/10")}
                          onClick={() => handleFeedbackClick('up')}
                          disabled={Boolean(feedback) || feedbackSubmitting}
                          aria-label={feedback === "up" ? "已提交有帮助反馈" : "有帮助"}
                        />
                      }
                    >
                      <ThumbsUp className={iconSize} fill={feedback === 'up' ? 'currentColor' : 'none'} />
                      {seniorMode && <span>有帮助</span>}
                    </TooltipTrigger>
                    <TooltipContent>赞</TooltipContent>
                  </Tooltip>

                  <Tooltip>
                    <TooltipTrigger
                      render={
                        <Button
                          variant="ghost"
                          size={btnSize}
                          className={cn(seniorActionClass, feedback === 'down' && "text-primary bg-primary/10")}
                          onClick={() => handleFeedbackClick('down')}
                          disabled={Boolean(feedback) || feedbackSubmitting}
                          aria-label={feedback === "down" ? "已提交没帮助反馈" : "没帮助"}
                        />
                      }
                    >
                      <ThumbsDown className={iconSize} fill={feedback === 'down' ? 'currentColor' : 'none'} />
                      {seniorMode && <span>没帮助</span>}
                    </TooltipTrigger>
                    <TooltipContent>踩</TooltipContent>
                  </Tooltip>

                  <div className="h-3 w-px bg-border/50 mx-0.5" />
                </>
              ) : null}

              {message.status === "done" && <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      variant="ghost"
                      size={btnSize}
                      className={seniorActionClass}
                      onClick={handleCopy}
                      aria-label="复制"
                    />
                  }
                >
                  {copied ? (
                    <Check className={cn(iconSize, "text-green-500")} />
                  ) : (
                    <Copy className={iconSize} />
                  )}
                  {seniorMode && <span>{copied ? "已复制" : "复制"}</span>}
                </TooltipTrigger>
                <TooltipContent>{copied ? "已复制" : "复制"}</TooltipContent>
              </Tooltip>}

              {!isUser && showRegenerate && (
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        variant="ghost"
                        size={btnSize}
                        className={seniorActionClass}
                        onClick={() => onRegenerate!(message.id)}
                        aria-label="重新生成"
                      />
                    }
                  >
                    <RefreshCw className={iconSize} />
                    {seniorMode && <span>重新生成</span>}
                  </TooltipTrigger>
                  <TooltipContent>重新生成</TooltipContent>
                </Tooltip>
              )}

              {!isUser && message.status === "done" && plainText && (
                <MessageVoiceReadButton
                  text={plainText}
                  seniorMode={seniorMode}
                  autoPlay={autoPlayEligible}
                  onAutoPlayConsumed={markAutoPlaybackConsumed}
                />
              )}

              {message.status === "done" && <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      variant="ghost"
                      size={btnSize}
                      className={seniorActionClass}
                      onClick={handleShare}
                      aria-label="分享"
                    />
                  }
                >
                  <Share2 className={iconSize} />
                  {seniorMode && <span>分享</span>}
                </TooltipTrigger>
                <TooltipContent>分享/导出</TooltipContent>
              </Tooltip>}

              {!isUser && message.status === "done" ? (
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button
                        variant="ghost"
                        size={btnSize}
                        className={seniorActionClass}
                        aria-label="更多"
                      />
                    }
                  >
                    <MoreHorizontal className={iconSize} />
                    {seniorMode && <span>更多</span>}
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" sideOffset={4}>
                    <DropdownMenuItem className={cn(seniorMode && "min-h-12 text-base")} onClick={handleEditInDoc}>
                      <FileEdit className="size-4" />
                      转为文档编辑
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      variant="destructive"
                      className={cn(seniorMode && "min-h-12 text-base")}
                      onClick={handleDelete}
                    >
                      <Trash2 className="size-4" />
                      删除
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : isUser ? (
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        variant="ghost"
                        size={btnSize}
                        className={seniorActionClass}
                        onClick={handleDelete}
                        aria-label="删除"
                      />
                    }
                  >
                    <Trash2 className={iconSize} />
                    {seniorMode && <span>删除</span>}
                  </TooltipTrigger>
                  <TooltipContent>删除</TooltipContent>
                </Tooltip>
              ) : null}
            </div>
          </div>
        )}
      </div>

      <Dialog
        open={showFeedbackDialog}
        onOpenChange={(open) => {
          if (!open && !feedbackSubmitting) dismissFeedbackDialog();
        }}
      >
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>
              {feedbackType === "up" ? "点赞反馈" : "点踩反馈"}
            </DialogTitle>
          </DialogHeader>
          <textarea
            value={feedbackText}
            onChange={(e) => setFeedbackText(e.target.value)}
            placeholder="请输入您的评价（可选）"
            disabled={feedbackSubmitting}
            className={cn(
              "w-full rounded-md border border-border bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 resize-none",
              seniorMode && "min-h-32 text-lg"
            )}
            rows={4}
          />
          <DialogFooter className="gap-2">
            <DialogClose render={<Button variant="outline" disabled={feedbackSubmitting} className={cn(seniorMode && "min-h-12 px-4 text-base")}>取消</Button>} />
            <Button
              className={cn(seniorMode && "min-h-12 px-4 text-base")}
              onClick={() => void submitMessageFeedback()}
              disabled={feedbackSubmitting}
            >
              {feedbackSubmitting ? "正在提交" : "提交反馈"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
