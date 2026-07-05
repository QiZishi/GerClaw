"use client";

import { useState } from "react";
import {
  Activity,
  Copy,
  Download,
  ExternalLink,
  Loader2,
  Pause,
  RefreshCw,
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
import { SubAgentTree } from "./blocks/SubAgentTree";
import { DecisionTimeline } from "./blocks/DecisionTimeline";
import { SearchResultCard } from "@/components/search/SearchResultCard";
import { FileTag } from "@/components/document/FileTag";
import { DocumentToolCard } from "@/components/document/DocumentToolCard";
import { MEDICAL_DISCLAIMER } from "@/lib/constants";
import type { Message, MessageBlock, RightPanelType } from "@/types";
import { toast } from "@/components/ui/toast";
import { useAudioPlayer } from "@/hooks/useAudioPlayer";

interface MessageBubbleProps {
  message: Message;
  onRegenerate?: (id: string) => void;
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
              "btn-icon",
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

export function MessageBubble({ message, onRegenerate }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const setRightPanel = useAppStore((s) => s.setRightPanel);

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

  const plainText = !isUser ? extractPlainText(message.blocks) : "";

  return (
    <div
      className={cn(
        "group flex gap-3 px-4 py-3",
        isUser ? "flex-row-reverse" : "flex-row"
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
            <Activity className="size-4" />
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
            "rounded-2xl px-4 py-2.5",
            isUser
              ? "bg-primary text-primary-foreground rounded-tr-sm"
              : "bg-muted text-foreground rounded-tl-sm"
          )}
        >
          <div className="space-y-2">
            {message.blocks.map((block) => {
              switch (block.kind) {
                case "text":
                  if (block.streaming) {
                    return (
                      <StreamingText
                        key={block.id}
                        content={block.content}
                        streaming
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
          <div className="text-xs text-muted-foreground px-2">
            {MEDICAL_DISCLAIMER}
          </div>
        )}

        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="btn-icon"
                  onClick={handleCopy}
                  aria-label="复制"
                />
              }
            >
              <Copy className="size-3.5" />
            </TooltipTrigger>
            <TooltipContent>{copied ? "已复制" : "复制"}</TooltipContent>
          </Tooltip>

          {!isUser && onRegenerate && (
            <Tooltip>
              <TooltipTrigger
                render={
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="btn-icon"
                    onClick={() => onRegenerate(message.id)}
                    aria-label="重新生成"
                  />
                }
              >
                <RefreshCw className="size-3.5" />
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
                    size="icon-sm"
                    className="btn-icon"
                    aria-label="导出"
                  />
                }
              >
                <Download className="size-3.5" />
              </TooltipTrigger>
              <TooltipContent>导出</TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>
    </div>
  );
}
