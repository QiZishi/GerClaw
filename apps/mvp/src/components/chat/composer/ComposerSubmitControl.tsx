"use client";

import { Mic, SendHorizonal, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface ComposerSubmitControlProps {
  isGenerating: boolean;
  isTranscribing: boolean;
  isSending: boolean;
  directiveSubmitting: "queue" | "steer" | null;
  hasDirectiveText: boolean;
  canSend: boolean;
  isOnline: boolean;
  asrAvailable: boolean;
  micDisabled: boolean;
  seniorMode: boolean;
  onSend: () => void;
  onStop?: () => void;
  onQueue: () => void;
  onSteer: () => void;
  onMicStart: () => void;
  onCancelTranscription: () => void;
}

export function ComposerSubmitControl(props: ComposerSubmitControlProps) {
  if (props.isGenerating) {
    return (
      <div
        className="flex flex-wrap items-center justify-end gap-2"
        aria-label="执行中的新要求"
      >
        <Button
          type="button"
          variant="outline"
          className={cn(
            "min-h-11 px-3 disabled:opacity-100 disabled:text-muted-foreground",
            props.seniorMode && "min-h-12 text-lg",
          )}
          disabled={
            !props.hasDirectiveText ||
            props.directiveSubmitting !== null ||
            !props.isOnline
          }
          onClick={props.onQueue}
        >
          {props.directiveSubmitting === "queue" ? "排队中" : "排队继续"}
        </Button>
        <Button
          type="button"
          className={cn(
            "min-h-11 px-3 disabled:bg-muted disabled:text-muted-foreground disabled:opacity-100",
            props.seniorMode && "min-h-12 text-lg",
          )}
          disabled={
            !props.hasDirectiveText ||
            props.directiveSubmitting !== null ||
            !props.isOnline
          }
          onClick={props.onSteer}
        >
          {props.directiveSubmitting === "steer" ? "调整中" : "立即调整"}
        </Button>
        <Button
          type="button"
          variant="destructive"
          className={cn(
            "min-h-11 gap-2 px-3 text-foreground disabled:opacity-100",
            props.seniorMode && "min-h-12 text-lg",
          )}
          onClick={props.onStop}
          aria-label="停止生成"
        >
          <Square className="size-4 fill-current" aria-hidden />
          <span>停止</span>
        </Button>
      </div>
    );
  }
  if (props.isTranscribing) {
    return (
      <div className="flex items-center gap-2 px-1" role="status" aria-live="polite">
        <span className={cn("whitespace-nowrap text-primary", props.seniorMode ? "text-lg" : "text-sm")}>
          正在识别语音
        </span>
        <Button
          type="button"
          variant="outline"
          size={props.seniorMode ? "default" : "sm"}
          className={cn("shrink-0", props.seniorMode && "min-h-12 px-3 text-base")}
          onClick={props.onCancelTranscription}
        >
          取消识别
        </Button>
      </div>
    );
  }
  if (props.canSend) {
    return (
      <IconAction
        label={props.isSending ? "正在提交" : "发送"}
        tooltip={props.isOnline ? "发送" : "网络已断开，请检查网络连接"}
        seniorMode={props.seniorMode}
        disabled={!props.isOnline || props.isSending}
        onClick={props.onSend}
        icon={<SendHorizonal className="size-4" aria-hidden />}
      />
    );
  }
  const micLabel = !props.isOnline
    ? "网络已断开，语音服务暂不可用"
    : !props.asrAvailable
      ? "语音服务暂时不可用"
      : "语音输入";
  return (
    <IconAction
      label={props.micDisabled ? "语音服务暂时不可用" : "语音输入"}
      tooltip={micLabel}
      seniorMode={props.seniorMode}
      disabled={props.micDisabled}
      onClick={props.onMicStart}
      icon={<Mic className={props.seniorMode ? "size-5" : "size-4"} aria-hidden />}
    />
  );
}

function IconAction({
  label,
  tooltip = label,
  seniorMode,
  variant = "default",
  disabled = false,
  onClick,
  icon,
}: {
  label: string;
  tooltip?: string;
  seniorMode: boolean;
  variant?: "default" | "destructive";
  disabled?: boolean;
  onClick?: () => void;
  icon: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant={variant}
            size={seniorMode ? "default" : "icon"}
            className={cn("btn-icon", seniorMode && "h-12 gap-2 px-3 text-base")}
            onClick={onClick}
            aria-label={label}
            disabled={disabled}
          />
        }
      >
        {icon}
        {seniorMode && <span>{label === "停止生成" ? "停止" : label}</span>}
      </TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  );
}
