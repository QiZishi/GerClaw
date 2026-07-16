"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import {
  AlertTriangle,
  Check,
  Copy,
  ExternalLink,
  FileEdit,
  MoreHorizontal,
  Pause,
  Play,
  RefreshCw,
  Share2,
  Square,
  Stethoscope,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  Volume2,
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
import { MarkdownRenderer } from "./MarkdownRenderer";
import { StreamingText } from "./blocks/StreamingText";
import { ThinkingBlock } from "./blocks/ThinkingBlock";
import { ToolCallBlock } from "./blocks/ToolCallBlock";
import { SimpleStepIndicator } from "./blocks/SimpleStepIndicator";
import { SubAgentTree } from "./blocks/SubAgentTree";
import { DecisionTimeline } from "./blocks/DecisionTimeline";
import { SearchResultCard } from "@/components/search/SearchResultCard";
import { SourceReferences } from "@/components/search/SourceReferences";
import { FileTag } from "@/components/document/FileTag";
import { DocumentToolCard } from "@/components/document/DocumentToolCard";
import { MEDICAL_DISCLAIMER } from "@/lib/constants";
import type { Message, MessageBlock, RightPanelType } from "@/types";
import { toast } from "@/components/ui/toast";
import { useAudioPlayer } from "@/hooks/useAudioPlayer";
import { InfoCollectionCard, StageIndicator } from "./InfoCollectionCard";
import { RuntimeApprovalCard } from "./blocks/RuntimeApprovalCard";
import { createFeedbackIdempotencyKey, submitFeedback } from "@/services/gerclaw/feedback";

function EmergencyWarningCard({
  message,
  seniorMode,
}: {
  message: string;
  seniorMode: boolean;
}) {
  return (
    <section
      aria-label="紧急医疗警告"
      role="alert"
      className={cn(
        "rounded-xl border-2 border-red-200 bg-red-700 p-4 text-white shadow-sm",
        seniorMode && "p-5"
      )}
    >
      <div className={cn("flex items-center gap-2 font-bold", seniorMode ? "text-xl" : "text-lg")}>
        <AlertTriangle aria-hidden className={seniorMode ? "size-6" : "size-5"} />
        <span>紧急医疗警告</span>
      </div>
      <p className={cn("mt-3 font-medium leading-relaxed", seniorMode ? "text-lg" : "text-base")}>
        {message}
      </p>
      <p className={cn("mt-3 font-bold leading-relaxed", seniorMode ? "text-lg" : "text-base")}>
        请立即拨打 120 急救电话或前往最近医院急诊科。
      </p>
      <p className="sr-only">系统已确认紧急风险，请立即按提示就医。</p>
    </section>
  );
}

/**
 * A streamed answer can contain useful partial text before the server rejects
 * its final safety check. Put that state at the top of the output, where it
 * cannot be missed after a long response.
 */
function IncompleteAnswerWarning({ seniorMode }: { seniorMode: boolean }) {
  return (
    <section
      role="alert"
      aria-label="回答未完成提醒"
      className={cn(
        "w-full rounded-xl border-2 border-amber-400 bg-amber-50 px-4 py-3 text-amber-950 shadow-sm dark:border-amber-500 dark:bg-amber-950/30 dark:text-amber-100",
        seniorMode && "p-4"
      )}
    >
      <div className={cn("flex items-center gap-2 font-bold", seniorMode ? "text-lg" : "text-base")}>
        <AlertTriangle aria-hidden className={cn("shrink-0", seniorMode ? "size-6" : "size-5")} />
        <span>本次回答未完成</span>
      </div>
      <p className={cn("mt-2 leading-relaxed", seniorMode ? "text-lg" : "text-sm")}>
        以下内容未经最终安全校验，请勿据此调整治疗或用药。您可以重新生成，或咨询医生。
      </p>
    </section>
  );
}

interface MessageBubbleProps {
  message: Message;
  onRegenerate?: (id: string) => void;
  onCopy?: (id: string) => void;
  onShare?: (id: string) => void;
  onDelete?: (id: string) => void;
  onEdit?: (id: string) => void;
  isLastMessage?: boolean;
}

function VoiceReadButton({ text, seniorMode, autoPlay }: { text: string; seniorMode: boolean; autoPlay: boolean }) {
  const { isPlaying, isPaused, isLoading, progress, play, pause, resume, stop } = useAudioPlayer();
  const autoPlaybackStartedRef = useRef(false);
  const autoPlaybackTimerRef = useRef<number | null>(null);

  const reportPlaybackError = () => toast.show("语音播放失败，请稍后重试");
  const start = () => void play(text).catch(reportPlaybackError);
  const continuePlayback = () => void resume().catch(reportPlaybackError);

  useEffect(() => {
    if (!autoPlay || autoPlaybackStartedRef.current || !text) return;
    autoPlaybackTimerRef.current = window.setTimeout(() => {
      autoPlaybackTimerRef.current = null;
      autoPlaybackStartedRef.current = true;
      // 自动朗读的失败不打断咨询；用户仍可点击“朗读”重试。
      void play(text).catch(() => undefined);
    }, 500);
    return () => {
      if (autoPlaybackTimerRef.current !== null) {
        window.clearTimeout(autoPlaybackTimerRef.current);
        autoPlaybackTimerRef.current = null;
      }
    };
  }, [autoPlay, play, text]);

  if (isLoading) {
    return (
      <Button
        variant="ghost"
        size={seniorMode ? "default" : "sm"}
        className={cn("gap-1.5 text-primary bg-primary/10", seniorMode && "min-h-12 px-3 text-base")}
        onClick={stop}
        aria-label="取消语音准备"
        aria-busy="true"
      >
        <Volume2 className={seniorMode ? "size-5" : "size-4"} />
        <span>正在准备，点击取消</span>
      </Button>
    );
  }

  if (isPlaying || isPaused) {
    return (
      <div className="inline-flex items-center gap-1.5" role="group" aria-label="语音播放控制">
        <div className="inline-flex items-center gap-1">
          <Button
            variant="ghost"
            size={seniorMode ? "default" : "icon-sm"}
            className={cn("text-primary bg-primary/10", seniorMode && "min-h-12 gap-1.5 px-3 text-base")}
            onClick={isPlaying ? pause : continuePlayback}
            aria-label={isPlaying ? "暂停语音" : "继续播放语音"}
          >
            {isPlaying ? <Pause className="size-4" /> : <Play className="size-4" />}
            {seniorMode && <span>{isPlaying ? "暂停" : "继续"}</span>}
          </Button>
          <Button
            variant="ghost"
            size={seniorMode ? "default" : "icon-sm"}
            className={cn(seniorMode && "min-h-12 gap-1.5 px-3 text-base")}
            onClick={stop}
            aria-label="停止语音"
          >
            <Square className="size-4" />
            {seniorMode && <span>停止</span>}
          </Button>
        </div>
        <div
          className={cn("h-1.5 w-16 overflow-hidden rounded-full bg-muted", seniorMode && "w-20")}
          role="progressbar"
          aria-label="语音播放进度"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(progress * 100)}
        >
          <div
            className="h-full rounded-full bg-primary motion-reduce:transition-none transition-[width] duration-150"
            style={{ width: `${Math.round(progress * 100)}%` }}
          />
        </div>
      </div>
    );
  }

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size={seniorMode ? "default" : "icon-sm"}
            className={cn(seniorMode && "min-h-12 gap-1.5 px-3 text-base")}
            onClick={start}
            aria-label="语音朗读"
          />
        }
      >
        <Volume2 className={seniorMode ? "size-5" : "size-4"} />
        {seniorMode && <span>朗读</span>}
      </TooltipTrigger>
      <TooltipContent>语音朗读</TooltipContent>
    </Tooltip>
  );
}

function formatElapsedTime(elapsedMs: number): string {
  const elapsedSeconds = Math.max(0, Math.floor(elapsedMs / 1000));
  const minutes = Math.floor(elapsedSeconds / 60);
  const seconds = elapsedSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

/**
 * A restrained, Codex-style activity indicator: three gentle dots plus a
 * real elapsed clock. It is displayed once per active response, rather than
 * starting a competing animation inside every nested tool card.
 */
function AssistantRunStatus({ startedAt, phase, seniorMode }: {
  startedAt: number;
  phase: string;
  seniorMode: boolean;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div
      className={cn(
        "flex w-full flex-wrap items-center gap-2 rounded-xl border border-primary/20 bg-primary/5 px-3 py-2 text-primary",
        seniorMode ? "min-h-12 text-base" : "text-sm"
      )}
    >
      <span className="inline-flex items-center gap-2 whitespace-nowrap" role="status">
        <span className="codex-activity-dots" aria-hidden>
          <span className="codex-activity-dot" />
          <span className="codex-activity-dot" />
          <span className="codex-activity-dot" />
        </span>
        <span className="font-medium">{phase}</span>
      </span>
      <span className="ml-auto shrink-0 whitespace-nowrap tabular-nums text-muted-foreground" aria-live="off">
        已执行 {formatElapsedTime(now - startedAt)}
      </span>
    </div>
  );
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
    "transition-all duration-200 ease-out",
    appeared ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
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
        {!isUser && errorAssistant && <IncompleteAnswerWarning seniorMode={seniorMode} />}
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
          <div className="space-y-2">
            {message.blocks.map((block) => {
              switch (block.kind) {
                case "text":
                  if (block.streaming) {
                    const textEmpty = !block.content;
                    const hidePlaceholder = textEmpty && hasActiveThinking;
                    return (
                      <StreamingText
                        key={block.id}
                        content={block.content}
                        streaming
                        citations={message.citations}
                        showPlaceholder={!hidePlaceholder}
                      />
                    );
                  }
                  return (
                    <MarkdownRenderer
                      key={block.id}
                      content={block.content}
                      citations={message.citations}
                    />
                  );
                case "image":
                  return (
                    <div key={block.id} className="mt-1 first:mt-0">
                      <Image
                        src={`data:${block.data.mimeType};base64,${block.data.base64}`}
                        alt={block.data.alt ?? "用户上传的图片"}
                        width={240}
                        height={320}
                        unoptimized
                        className="max-w-[240px] max-h-[320px] w-auto h-auto rounded-lg object-cover cursor-pointer hover:opacity-90 transition-opacity"
                        onClick={() => window.open(`data:${block.data.mimeType};base64,${block.data.base64}`, "_blank")}
                      />
                    </div>
                  );
                case "thinking":
                  return (
                    <ThinkingBlock key={block.id} data={block.data} />
                  );
                case "tool_call":
                  return (
                    <ToolCallBlock key={block.id} data={block.data} />
                  );
                case "sub_agent":
                  return <SubAgentTree key={block.id} data={block.data} />;
                case "decision":
                  return (
                    <DecisionTimeline key={block.id} data={block.data} />
                  );
                case "search_results":
                  return (
                    <div
                      key={block.id}
                      className="space-y-2 not-last:mt-2"
                    >
                      {block.data.map((item, idx) => (
                        <SearchResultCard
                          key={item.id}
                          item={item}
                          index={idx + 1}
                        />
                      ))}
                    </div>
                  );
                case "file":
                  return (
                    <div key={block.id} className="space-y-2">
                      <FileTag data={block.data} />
                      <DocumentToolCard data={block.data} />
                    </div>
                  );
                case "info_collection":
                  return (
                    <div key={block.id} className="mt-1 first:mt-0 w-full">
                      <InfoCollectionCard
                        fields={block.data.fields}
                        compact={seniorMode}
                      />
                    </div>
                  );
                case "stage_indicator":
                  return (
                    <div key={block.id} className="mt-1 first:mt-0 w-full">
                      <StageIndicator
                        title={block.data.title}
                        description={block.data.description}
                      />
                    </div>
                  );
                case "runtime_approval":
                  return <RuntimeApprovalCard key={block.id} data={block.data} />;
                case "emergency_alert":
                  return (
                    <EmergencyWarningCard
                      key={block.id}
                      message={block.data.message}
                      seniorMode={seniorMode}
                    />
                  );
                case "question_card":
                  if (block.data.submitted) {
                    return (
                      <div key={block.id} className="mt-1 first:mt-0 w-full">
                        <div className="rounded-2xl border border-border/60 bg-gradient-to-br from-blue-50/80 to-indigo-50/50 dark:from-blue-950/20 dark:to-indigo-950/10 p-4 shadow-sm">
                          <div className="flex items-center gap-2 mb-3">
                            <span className="text-lg">📋</span>
                            <span className={cn("font-semibold text-foreground", seniorMode ? "text-lg" : "text-base")}>信息补充</span>
                            <span className={cn("text-muted-foreground bg-muted/60 px-2 py-0.5 rounded-full", seniorMode ? "text-lg" : "text-xs")}>
                              第{block.data.round}轮
                            </span>
                          </div>
                          <div className="space-y-2">
                            {block.data.questions.map((q) => {
                              const answer = block.data.answers[q.id] || "";
                              return (
                                <div key={q.id} className="space-y-0.5">
                                  <div className={cn("font-medium text-foreground flex items-center gap-2", seniorMode ? "text-lg" : "text-sm")}>
                                    <Check className="size-4 text-green-500 shrink-0" />
                                    {q.label}
                                  </div>
                                  <p className={cn("text-foreground/80 pl-6", seniorMode ? "text-lg" : "text-xs")}>
                                    {answer}
                                  </p>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    );
                  }
                  return null;
                case "action":
                  return (
                    <div
                      key={block.id}
                      className="rounded-lg border border-primary/30 bg-primary/5 p-3 space-y-2"
                    >
                      <p className="text-sm leading-relaxed">{block.summary}</p>
                      <Button
                        variant="default"
                        size="sm"
                        onClick={() => handleViewReport(block.panelType)}
                        className="gap-1.5"
                      >
                        <ExternalLink className="size-3.5" />
                        {block.buttonLabel}
                      </Button>
                    </div>
                  );
                default:
                  return null;
              }
            })}
          </div>
        </div>

        {message.hasDisclaimer && !hasInlineDisclaimer && (
          <div className={cn(
            "text-muted-foreground px-2",
            seniorMode ? "text-lg leading-relaxed" : "text-[11px]"
          )}>
            {MEDICAL_DISCLAIMER}
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
                <VoiceReadButton
                  text={plainText}
                  seniorMode={seniorMode}
                  autoPlay={role === "patient" && seniorMode && autoTtsPlayback && ttsAvailable && Boolean(isLastMessage)}
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
