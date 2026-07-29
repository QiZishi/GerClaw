"use client";

import { useEffect, useState } from "react";
import { Stethoscope } from "lucide-react";

import { MessageBody } from "@/components/chat/message/MessageBody";
import { MessageActions } from "@/components/chat/message/MessageActions";
import {
  AssistantRunStatus,
  IncompleteAnswerWarning,
} from "@/components/chat/message/MessageStatusNotices";
import { SimpleStepIndicator } from "@/components/chat/blocks/SimpleStepIndicator";
import { SourceReferences } from "@/components/search/SourceReferences";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { MEDICAL_DISCLAIMER } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import type { Message, RightPanelType } from "@/types";

interface MessageBubbleProps {
  message: Message;
  onRegenerate?: (id: string) => void;
  onCopy?: (id: string) => void;
  onShare?: (id: string) => void;
  onDelete?: (id: string) => void;
  onEdit?: (id: string) => void;
  isLastMessage?: boolean;
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
  const [appeared, setAppeared] = useState(false);
  const seniorMode = useAppStore((state) => state.seniorMode);
  const setRightPanel = useAppStore((state) => state.setRightPanel);
  const setPanelContent = useAppStore((state) => state.setPanelContent);
  const isUser = message.role === "user";
  const companionMode = message.workflow === "companion";
  const hasInlineDisclaimer = message.blocks.some(
    (block) =>
      block.kind === "text" &&
      (block.content.includes(MEDICAL_DISCLAIMER) || block.content.includes("免责声明")),
  );
  const hasActiveThinking = !isUser && message.blocks.some(
    (block) => block.kind === "thinking" && block.data.status === "thinking",
  );

  useEffect(() => {
    const timer = window.setTimeout(() => setAppeared(true), 10);
    return () => window.clearTimeout(timer);
  }, []);

  const handleViewReport = (panelType: RightPanelType) => {
    const session = useChatStore
      .getState()
      .sessions.find((item) => item.id === message.sessionId);
    setRightPanel(panelType);
    setPanelContent(
      session?.panelType === panelType ? session.panelContent ?? "" : "",
    );
  };

  return (
    <div
      data-message-bubble
      className={cn(
        "group flex gap-3 px-4 py-4 transition-[transform,opacity] duration-200 motion-reduce:transition-opacity",
        isUser ? "flex-row-reverse" : "flex-row",
        appeared ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0 motion-reduce:translate-y-0",
      )}
    >
      <Avatar className="mt-0.5 shrink-0" size="default">
        <AvatarFallback
          className={cn(
            isUser ? "bg-muted text-foreground" : "bg-secondary text-secondary-foreground",
          )}
        >
          {isUser ? <span className="text-xs">我</span> : <Stethoscope className="size-4" aria-hidden />}
        </AvatarFallback>
      </Avatar>
      <div
        className={cn(
          "flex min-w-0 flex-col gap-2",
          isUser ? "max-w-[calc(100%-3rem)] items-end sm:max-w-[80%]" : "w-full max-w-3xl items-start",
        )}
      >
        {!isUser && message.status === "streaming" && (
          <AssistantRunStatus
            startedAt={message.createdAt}
            phase={hasActiveThinking ? "正在分析您的问题" : "正在生成答复"}
            seniorMode={seniorMode}
          />
        )}
        {!isUser && message.status === "error" && (
          <IncompleteAnswerWarning seniorMode={seniorMode} companionMode={companionMode} />
        )}
        <div
          className={cn(
            isUser
              ? "rounded-2xl rounded-tr-sm bg-muted px-4 py-2.5 text-foreground"
              : "w-full px-1 py-1 text-foreground",
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
          <div className={cn("px-2 text-muted-foreground", seniorMode ? "text-lg leading-relaxed" : "text-[11px]")}>
            {companionMode
              ? "此模式提供情感支持，不替代医疗咨询、心理治疗或紧急援助。"
              : MEDICAL_DISCLAIMER}
          </div>
        )}
        {!isUser && message.citations?.length && message.status === "done" ? (
          <div className="w-full px-1">
            <SourceReferences citations={message.citations} />
          </div>
        ) : null}
        <div className="relative">
          <MessageActions
            message={message}
            isLastMessage={isLastMessage}
            onRegenerate={onRegenerate}
            onCopy={onCopy}
            onShare={onShare}
            onDelete={onDelete}
            onEdit={onEdit}
          />
        </div>
      </div>
    </div>
  );
}
