"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import {
  Check,
  Copy,
  ExternalLink,
  Loader2,
  Pause,
  RefreshCw,
  Share2,
  Stethoscope,
  ThumbsDown,
  ThumbsUp,
  Volume2,
} from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAppStore } from "@/stores/appStore";
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
import { exportToMarkdown } from "@/lib/export";
import { InfoCollectionCard } from "./InfoCollectionCard";

interface MessageBubbleProps {
  message: Message;
  onRegenerate?: (id: string) => void;
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
    icon = <Pause className={cn(seniorMode ? "size-4" : "size-3.5")} />;
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

export function MessageBubble({ message, onRegenerate, isLastMessage }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);
  const [appeared, setAppeared] = useState(false);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const setRightPanel = useAppStore((s) => s.setRightPanel);

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
      setTimeout(() => setCopied(false), 1500);
    });
  };

  const handleFeedbackUp = () => {
    if (feedback === 'up') {
      setFeedback(null);
    } else {
      setFeedback('up');
      toast.show("感谢反馈");
    }
  };

  const handleFeedbackDown = () => {
    if (feedback === 'down') {
      setFeedback(null);
    } else {
      setFeedback('down');
      toast.show("感谢反馈");
    }
  };

  const handleShare = () => {
    try {
      const textContent = extractPlainText(message.blocks);
      const title = textContent.slice(0, 50).replace(/[#*`_~\[\]()>|-]/g, "").trim() || "AI回复";
      exportToMarkdown({
        title: `GerClaw回复 - ${title}`,
        content: textContent,
        subtitle: "单条消息导出",
      });
      toast.show("消息已导出为 Markdown");
    } catch {
      toast.show("导出失败，请重试");
    }
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

        {message.status === "done" && (
          <div data-message-actions className={cn(
            "flex items-center gap-0.5 transition-opacity duration-150",
            "rounded-full bg-muted/40 border border-border/40 px-1 py-0.5",
            seniorMode
              ? "opacity-100"
              : "opacity-0 group-hover:opacity-100 focus-within:opacity-100"
          )}>
            {!isUser && (
              <>
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        variant="ghost"
                        size={btnSize}
                        className={cn(feedback === 'up' && "text-primary bg-primary/10")}
                        onClick={handleFeedbackUp}
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
                        onClick={handleFeedbackDown}
                        aria-label="踩"
                      />
                    }
                  >
                    <ThumbsDown className={iconSize} fill={feedback === 'down' ? 'currentColor' : 'none'} />
                  </TooltipTrigger>
                  <TooltipContent>踩</TooltipContent>
                </Tooltip>

                <div className="h-3 w-px bg-border/50 mx-0.5" />
              </>
            )}

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

            {!isUser && plainText && (
              <VoiceReadButton text={plainText} seniorMode={seniorMode} />
            )}

            {!isUser && (
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
                <TooltipContent>导出</TooltipContent>
              </Tooltip>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
