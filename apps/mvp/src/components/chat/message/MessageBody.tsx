"use client";

import Image from "next/image";
import { Check, ExternalLink } from "lucide-react";

import { DecisionTimeline } from "@/components/chat/blocks/DecisionTimeline";
import { RuntimeApprovalCard } from "@/components/chat/blocks/RuntimeApprovalCard";
import { StreamingText } from "@/components/chat/blocks/StreamingText";
import { SubAgentTree } from "@/components/chat/blocks/SubAgentTree";
import { ThinkingBlock } from "@/components/chat/blocks/ThinkingBlock";
import { EmergencyWarningCard } from "@/components/chat/message/MessageStatusNotices";
import { InfoCollectionCard, StageIndicator } from "@/components/chat/InfoCollectionCard";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";
import { DocumentToolCard } from "@/components/document/DocumentToolCard";
import { FileTag } from "@/components/document/FileTag";
import { SearchResultCard } from "@/components/search/SearchResultCard";
import { Button } from "@/components/ui/button";
import { stripCitationMarkers } from "@/lib/citation-markers";
import { cn } from "@/lib/utils";
import type { Message, RightPanelType } from "@/types";

export function MessageBody({
  message,
  seniorMode,
  hasActiveThinking,
  onViewReport,
}: {
  message: Message;
  seniorMode: boolean;
  hasActiveThinking: boolean;
  onViewReport: (panelType: RightPanelType) => void;
}) {
  return (
    <div className="space-y-2">
      {message.blocks.map((block) => {
        switch (block.kind) {
          case "text":
            return block.streaming ? (
              <StreamingText
                key={block.id}
                content={stripCitationMarkers(block.content)}
                streaming
                showPlaceholder={Boolean(block.content) || !hasActiveThinking}
              />
            ) : (
              <MarkdownRenderer
                key={block.id}
                content={stripCitationMarkers(block.content)}
              />
            );
          case "image":
            return (
              <div key={block.id} className="relative mt-1 size-60 max-w-full first:mt-0">
                <Image
                  src={`data:${block.data.mimeType};base64,${block.data.base64}`}
                  alt={block.data.alt ?? "用户上传的图片"}
                  fill
                  sizes="240px"
                  unoptimized
                  className="cursor-pointer rounded-lg object-cover transition-opacity hover:opacity-90"
                  onClick={() => window.open(`data:${block.data.mimeType};base64,${block.data.base64}`, "_blank")}
                />
              </div>
            );
          case "thinking":
            return <ThinkingBlock key={block.id} data={block.data} />;
          case "tool_call":
            // Tool names, durations and completion states belong in telemetry.
            // The running answer already has one concise reader-facing status.
            return null;
          case "sub_agent":
            return <SubAgentTree key={block.id} data={block.data} />;
          case "decision":
            return <DecisionTimeline key={block.id} data={block.data} />;
          case "search_results":
            return (
              <div key={block.id} className="space-y-2 not-last:mt-2">
                {block.data.map((item, index) => (
                  <SearchResultCard key={item.id} item={item} index={index + 1} />
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
              <div key={block.id} className="mt-1 w-full first:mt-0">
                <InfoCollectionCard fields={block.data.fields} compact={seniorMode} />
              </div>
            );
          case "stage_indicator":
            return (
              <div key={block.id} className="mt-1 w-full first:mt-0">
                <StageIndicator title={block.data.title} description={block.data.description} />
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
            if (!block.data.submitted) return null;
            return (
              <div key={block.id} className="mt-1 w-full first:mt-0">
                <div className="rounded-2xl border border-border/60 bg-muted/40 p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <span aria-hidden>📋</span>
                    <span className={cn("font-semibold", seniorMode ? "text-lg" : "text-base")}>
                      信息补充
                    </span>
                    <span className={cn("rounded-full bg-muted px-2 py-0.5 text-muted-foreground", seniorMode ? "text-base" : "text-xs")}>
                      第{block.data.round}轮
                    </span>
                  </div>
                  <div className="space-y-2">
                    {block.data.questions.map((question) => (
                      <div key={question.id} className="space-y-0.5">
                        <div className={cn("flex items-center gap-2 font-medium", seniorMode ? "text-lg" : "text-sm")}>
                          <Check className="size-4 shrink-0 text-green-600" aria-hidden />
                          {question.label}
                        </div>
                        <p className={cn("pl-6 text-foreground/80", seniorMode ? "text-lg" : "text-xs")}>
                          {block.data.answers[question.id] || ""}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          case "action":
            return (
              <div key={block.id} className="space-y-2 rounded-lg border border-primary/30 bg-primary/5 p-3">
                <p className="text-sm leading-relaxed">{block.summary}</p>
                <Button size="sm" onClick={() => onViewReport(block.panelType)} className="gap-1.5">
                  <ExternalLink className="size-3.5" aria-hidden />
                  {block.buttonLabel}
                </Button>
              </div>
            );
          default:
            return null;
        }
      })}
    </div>
  );
}
