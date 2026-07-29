"use client";

import { useCallback, useEffect, useState } from "react";

import { useMessageFeedback } from "@/components/chat/message/useMessageFeedback";
import { toast } from "@/components/ui/toast";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";
import type { Message, MessageBlock } from "@/types";

function extractPlainText(blocks: MessageBlock[]): string {
  return blocks
    .filter((block): block is Extract<MessageBlock, { kind: "text" }> => block.kind === "text")
    .map((block) => block.content)
    .join("\n")
    .replace(/[#*`_~\[\]()>|-]/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function useMessageActions({
  message,
  onCopy,
  onShare,
  onDelete,
  onEdit,
}: {
  message: Message;
  onCopy?: (id: string) => void;
  onShare?: (id: string) => void;
  onDelete?: (id: string) => void;
  onEdit?: (id: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  const role = useAppStore((state) => state.role);
  const seniorMode = useAppStore((state) => state.seniorMode);
  const autoTtsPlayback = useAppStore((state) => state.autoTtsPlayback);
  const ttsAvailable = useAppStore((state) => state.ttsAvailable);
  const setRightPanel = useAppStore((state) => state.setRightPanel);
  const setPanelContent = useAppStore((state) => state.setPanelContent);
  const updateMessage = useChatStore((state) => state.updateMessage);
  const feedback = useMessageFeedback(message);
  const plainText = extractPlainText(message.blocks);
  const autoPlayEligible = Boolean(
    message.autoTtsPending &&
    role === "patient" &&
    seniorMode &&
    autoTtsPlayback &&
    ttsAvailable,
  );
  const markAutoPlaybackConsumed = useCallback(() => {
    updateMessage(message.id, { autoTtsPending: false });
  }, [message.id, updateMessage]);

  useEffect(() => {
    if (message.autoTtsPending && !autoPlayEligible) markAutoPlaybackConsumed();
  }, [autoPlayEligible, markAutoPlaybackConsumed, message.autoTtsPending]);

  const copy = async () => {
    try {
      if (!navigator.clipboard) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(plainText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
      toast.show("已复制");
      onCopy?.(message.id);
    } catch {
      toast.show("复制失败，请手动选择文字");
    }
  };
  const editInDoc = () => {
    setRightPanel("doc-editor");
    setPanelContent(plainText);
    onEdit?.(message.id);
  };

  return {
    seniorMode,
    plainText,
    copied,
    autoPlayEligible,
    markAutoPlaybackConsumed,
    feedback,
    copy,
    editInDoc,
    share: () => onShare?.(message.id),
    deleteMessage: () => onDelete?.(message.id),
  };
}
