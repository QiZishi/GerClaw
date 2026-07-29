"use client";

import type { ReactNode } from "react";
import {
  Check,
  Copy,
  FileEdit,
  MoreHorizontal,
  RefreshCw,
  Share2,
  ThumbsDown,
  ThumbsUp,
  Trash2,
} from "lucide-react";

import { MessageFeedbackDialog } from "@/components/chat/message/MessageFeedbackDialog";
import { MessageVoiceReadButton } from "@/components/chat/message/MessageVoiceReadButton";
import { useMessageActions } from "@/components/chat/message/useMessageActions";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Message } from "@/types";

interface MessageActionsProps {
  message: Message;
  isLastMessage?: boolean;
  onRegenerate?: (id: string) => void;
  onCopy?: (id: string) => void;
  onShare?: (id: string) => void;
  onDelete?: (id: string) => void;
  onEdit?: (id: string) => void;
}

export function MessageActions(props: MessageActionsProps) {
  const actions = useMessageActions(props);
  const { message } = props;
  const isUser = message.role === "user";
  const terminal = message.status === "done" || message.status === "stopped" || message.status === "error";
  const hasEmergency = !isUser && message.blocks.some((block) => block.kind === "emergency_alert");
  if (!terminal || hasEmergency) return null;

  const showRegenerate = !isUser && props.isLastMessage && props.onRegenerate;
  const supportsRunFeedback = Boolean(message.executionRunId);
  const canFeedback = !isUser && message.status === "done" && (supportsRunFeedback || message.traceId);
  const feedback = actions.feedback;

  return (
    <>
      <div
        data-message-actions
        data-html2canvas-ignore
        className={cn(
          "flex items-center gap-0.5 rounded-full border border-border/40 bg-muted/40 px-1 py-0.5 transition-opacity",
          actions.seniorMode || message.status === "error"
            ? "flex-wrap gap-1 rounded-xl px-2 py-1 opacity-100"
            : "opacity-0 group-hover:opacity-100 focus-within:opacity-100",
        )}
      >
        {canFeedback && (
          <>
            <ActionButton
              label={feedback.feedback === "up" && supportsRunFeedback ? "撤销有帮助反馈" : feedback.feedback === "up" ? "已提交有帮助反馈" : "有帮助"}
              tooltip="赞"
              seniorLabel="有帮助"
              seniorMode={actions.seniorMode}
              active={feedback.feedback === "up"}
              disabled={feedback.feedbackSubmitting || (!supportsRunFeedback && Boolean(feedback.feedback))}
              onClick={() => feedback.handleFeedbackClick("up")}
              icon={<ThumbsUp className="size-4" fill={feedback.feedback === "up" ? "currentColor" : "none"} />}
            />
            <ActionButton
              label={feedback.feedback === "down" && supportsRunFeedback ? "撤销没帮助反馈" : feedback.feedback === "down" ? "已提交没帮助反馈" : "没帮助"}
              tooltip="踩"
              seniorLabel="没帮助"
              seniorMode={actions.seniorMode}
              active={feedback.feedback === "down"}
              disabled={feedback.feedbackSubmitting || (!supportsRunFeedback && Boolean(feedback.feedback))}
              onClick={() => feedback.handleFeedbackClick("down")}
              icon={<ThumbsDown className="size-4" fill={feedback.feedback === "down" ? "currentColor" : "none"} />}
            />
            <div className="mx-0.5 h-3 w-px bg-border/50" />
          </>
        )}
        {message.status === "done" && (
          <ActionButton
            label={actions.copied ? "已复制" : "复制"}
            seniorMode={actions.seniorMode}
            onClick={() => void actions.copy()}
            icon={actions.copied ? <Check className="size-4 text-green-600" /> : <Copy className="size-4" />}
          />
        )}
        {showRegenerate && (
          <ActionButton
            label="重新生成"
            seniorMode={actions.seniorMode}
            onClick={() => props.onRegenerate?.(message.id)}
            icon={<RefreshCw className="size-4" />}
          />
        )}
        {!isUser && message.status === "done" && actions.plainText && (
          <MessageVoiceReadButton
            text={actions.plainText}
            seniorMode={actions.seniorMode}
            autoPlay={actions.autoPlayEligible}
            onAutoPlayConsumed={actions.markAutoPlaybackConsumed}
          />
        )}
        {message.status === "done" && (
          <ActionButton
            label="分享"
            tooltip="分享/导出"
            seniorMode={actions.seniorMode}
            onClick={actions.share}
            icon={<Share2 className="size-4" />}
          />
        )}
        {!isUser && message.status === "done" ? (
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button
                  variant="ghost"
                  size={actions.seniorMode ? "default" : "icon-sm"}
                  className={cn(actions.seniorMode && "min-h-12 gap-1.5 px-3 text-base")}
                  aria-label="更多"
                />
              }
            >
              <MoreHorizontal className="size-4" />
              {actions.seniorMode && <span>更多</span>}
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" sideOffset={4}>
              <DropdownMenuItem onClick={actions.editInDoc}>
                <FileEdit className="size-4" />转为文档编辑
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" onClick={actions.deleteMessage}>
                <Trash2 className="size-4" />删除
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : isUser ? (
          <ActionButton
            label="删除"
            seniorMode={actions.seniorMode}
            onClick={actions.deleteMessage}
            icon={<Trash2 className="size-4" />}
          />
        ) : null}
      </div>
      <MessageFeedbackDialog
        open={feedback.showFeedbackDialog}
        type={feedback.feedbackType}
        text={feedback.feedbackText}
        submitting={feedback.feedbackSubmitting}
        seniorMode={actions.seniorMode}
        onOpenChange={(open) => {
          if (!open && !feedback.feedbackSubmitting) feedback.dismissFeedbackDialog();
          else feedback.setShowFeedbackDialog(open);
        }}
        onTextChange={feedback.setFeedbackText}
        onSubmit={() => void feedback.submitLegacyFeedback()}
      />
    </>
  );
}

function ActionButton({
  label,
  tooltip = label,
  seniorLabel = label,
  seniorMode,
  active = false,
  disabled = false,
  onClick,
  icon,
}: {
  label: string;
  tooltip?: string;
  seniorLabel?: string;
  seniorMode: boolean;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
  icon: ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size={seniorMode ? "default" : "icon-sm"}
            className={cn(active && "bg-primary/10 text-primary", seniorMode && "min-h-12 gap-1.5 px-3 text-base")}
            onClick={onClick}
            disabled={disabled}
            aria-label={label}
          />
        }
      >
        {icon}
        {seniorMode && <span>{seniorLabel}</span>}
      </TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  );
}
