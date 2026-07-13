"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import {
  Check,
  Copy,
  ExternalLink,
  FileEdit,
  Loader2,
  MoreHorizontal,
  RefreshCw,
  Share2,
  Stethoscope,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  Volume2,
  VolumeX,
  AlertTriangle,
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

interface MessageBubbleProps {
  message: Message;
  onRegenerate?: (id: string) => void;
  onCopy?: (id: string) => void;
  onShare?: (id: string) => void;
  onDelete?: (id: string) => void;
  onEdit?: (id: string) => void;
  isLastMessage?: boolean;
}

function VoiceReadButton({ text, seniorMode }: { text: string; seniorMode: boolean }) {
  const { isPlaying, isLoading, play, stop } = useAudioPlayer();

  const handleClick = () => {
    try {
      if (isPlaying || isLoading) {
        stop();
      } else {
        play(text);
      }
    } catch {
      toast.show("语音播放失败");
    }
  };

  let icon;
  let label;
  if (isLoading) {
    icon = <Loader2 className={cn("animate-spin", seniorMode ? "size-4" : "size-3.5")} />;
    label = "加载中";
  } else if (isPlaying) {
    icon = <VolumeX className={cn(seniorMode ? "size-4" : "size-3.5")} />;
    label = "停止播放";
  } else {
    icon = <Volume2 className={cn(seniorMode ? "size-4" : "size-3.5")} />;
    label = "语音朗读";
  }

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size={seniorMode ? "icon" : "icon-sm"}
            className={cn(
              (isPlaying || isLoading) && "text-primary bg-primary/10"
            )}
            onClick={handleClick}
            aria-label={label}
          />
        }
      >
        {icon}
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
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
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const setRightPanel = useAppStore((s) => s.setRightPanel);
  const setPanelContent = useAppStore((s) => s.setPanelContent);
  const setMessageFeedback = useChatStore((s) => s.setMessageFeedback);

  const feedback = message.feedback ?? null;

  useEffect(() => {
    const timer = setTimeout(() => setAppeared(true), 10);
    return () => clearTimeout(timer);
  }, []);

  const handleViewReport = (panelType: RightPanelType) => {
    setRightPanel(panelType);
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
    if (feedback === type) {
      setMessageFeedback(message.id, null);
    } else {
      setMessageFeedback(message.id, type);
      toast.show("感谢反馈");
    }
  };

  const handleEditInDoc = () => {
    const textContent = extractPlainText(message.blocks);
    setPanelContent(textContent);
    setRightPanel("doc-editor");
    onEdit?.(message.id);
  };

  const handleDelete = () => {
    setShowDeleteConfirm(true);
  };

  const confirmDelete = () => {
    setShowDeleteConfirm(false);
    onDelete?.(message.id);
  };

  const handleShare = () => {
    onShare?.(message.id);
  };

  const plainText = !isUser ? extractPlainText(message.blocks) : "";
  const hasActiveThinking = !isUser && message.blocks.some(
    (b) => b.kind === "thinking" && b.data.status === "thinking"
  );
  const messageAnimation = cn(
    "transition-all duration-200 ease-out",
    appeared ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
  );
  const iconSize = seniorMode ? "size-4" : "size-3.5";
  const btnSize = seniorMode ? "icon" : "icon-sm";
  const showRegenerate = !isUser && isLastMessage && onRegenerate && message.status === "done";

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
          "flex flex-col gap-2 min-w-0 max-w-[80%]",
          isUser ? "items-end" : "items-start"
        )}
      >
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
                case "question_card":
                  if (block.data.submitted) {
                    return (
                      <div key={block.id} className="mt-1 first:mt-0 w-full">
                        <div className="rounded-2xl border border-border/60 bg-gradient-to-br from-blue-50/80 to-indigo-50/50 dark:from-blue-950/20 dark:to-indigo-950/10 p-4 shadow-sm">
                          <div className="flex items-center gap-2 mb-3">
                            <span className="text-lg">📋</span>
                            <span className={cn("font-semibold text-foreground", seniorMode ? "text-lg" : "text-base")}>信息补充</span>
                            <span className={cn("text-muted-foreground bg-muted/60 px-2 py-0.5 rounded-full", seniorMode ? "text-sm" : "text-xs")}>
                              第{block.data.round}轮
                            </span>
                          </div>
                          <div className="space-y-2">
                            {block.data.questions.map((q) => {
                              const answer = block.data.answers[q.id] || "";
                              return (
                                <div key={q.id} className="space-y-0.5">
                                  <div className={cn("font-medium text-foreground flex items-center gap-2", seniorMode ? "text-base" : "text-sm")}>
                                    <Check className="size-4 text-green-500 shrink-0" />
                                    {q.label}
                                  </div>
                                  <p className={cn("text-foreground/80 pl-6", seniorMode ? "text-sm" : "text-xs")}>
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

        {message.hasDisclaimer && (
          <div className={cn(
            "text-muted-foreground px-2",
            seniorMode ? "text-xs" : "text-[11px]"
          )}>
            {MEDICAL_DISCLAIMER}
          </div>
        )}

        {!isUser && message.citations && message.citations.length > 0 && message.status === "done" && (
          <div className="px-1 w-full">
            <SourceReferences citations={message.citations} />
          </div>
        )}

        {!isUser && message.status === "done" && (
          <div className="relative">
            <div
              data-message-actions
              data-html2canvas-ignore
              className={cn(
                "flex items-center gap-0.5 transition-opacity duration-150",
                "rounded-full bg-muted/40 border border-border/40 px-1 py-0.5",
                seniorMode
                  ? "opacity-100"
                  : "opacity-0 group-hover:opacity-100 focus-within:opacity-100"
              )}
            >
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      variant="ghost"
                      size={btnSize}
                      className={cn(feedback === 'up' && "text-primary bg-primary/10")}
                      onClick={() => handleFeedbackClick('up')}
                      aria-label="赞"
                    />
                  }
                >
                  <ThumbsUp className={iconSize} fill={feedback === 'up' ? 'currentColor' : 'none'} />
                </TooltipTrigger>
                <TooltipContent>赞</TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      variant="ghost"
                      size={btnSize}
                      className={cn(feedback === 'down' && "text-primary bg-primary/10")}
                      onClick={() => handleFeedbackClick('down')}
                      aria-label="踩"
                    />
                  }
                >
                  <ThumbsDown className={iconSize} fill={feedback === 'down' ? 'currentColor' : 'none'} />
                </TooltipTrigger>
                <TooltipContent>踩</TooltipContent>
              </Tooltip>

              <div className="h-3 w-px bg-border/50 mx-0.5" />

              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      variant="ghost"
                      size={btnSize}
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
                </TooltipTrigger>
                <TooltipContent>{copied ? "已复制" : "复制"}</TooltipContent>
              </Tooltip>

              {showRegenerate && (
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        variant="ghost"
                        size={btnSize}
                        onClick={() => onRegenerate!(message.id)}
                        aria-label="重新生成"
                      />
                    }
                  >
                    <RefreshCw className={iconSize} />
                  </TooltipTrigger>
                  <TooltipContent>重新生成</TooltipContent>
                </Tooltip>
              )}

              {plainText && (
                <VoiceReadButton text={plainText} seniorMode={seniorMode} />
              )}

              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      variant="ghost"
                      size={btnSize}
                      onClick={handleShare}
                      aria-label="分享"
                    />
                  }
                >
                  <Share2 className={iconSize} />
                </TooltipTrigger>
                <TooltipContent>分享/导出</TooltipContent>
              </Tooltip>

              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      variant="ghost"
                      size={btnSize}
                      aria-label="更多"
                    />
                  }
                >
                  <MoreHorizontal className={iconSize} />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" sideOffset={4}>
                  <DropdownMenuItem onClick={handleEditInDoc}>
                    <FileEdit className="size-4" />
                    转为文档编辑
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    variant="destructive"
                    onClick={handleDelete}
                  >
                    <Trash2 className="size-4" />
                    删除
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        )}
      </div>

      <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="size-5 text-amber-500" />
              确认删除？
            </DialogTitle>
          </DialogHeader>
          <p className={cn("text-muted-foreground", seniorMode ? "text-base" : "text-sm")}>
            删除后该条消息将无法恢复，确定要删除吗？
          </p>
          <DialogFooter className="gap-2">
            <DialogClose render={<Button variant="outline">取消</Button>} />
            <Button variant="destructive" onClick={confirmDelete}>
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
