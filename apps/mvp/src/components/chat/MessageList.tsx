"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MessageBubble } from "./MessageBubble";
import type { Message } from "@/types";

interface MessageListProps {
  messages: Message[];
  onRegenerate?: (id: string) => void;
}

/**
 * 消息列表
 * 自动滚动到底部，用户手动上滚后显示"回到底部"悬浮按钮
 */
export function MessageList({ messages, onRegenerate }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [showScrollDown, setShowScrollDown] = useState(false);

  // 自动滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  // 监听滚动，显示/隐藏"回到底部"按钮
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = el;
      const distanceToBottom = scrollHeight - scrollTop - clientHeight;
      setShowScrollDown(distanceToBottom > 200);
    };
    el.addEventListener("scroll", handleScroll);
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="relative flex-1 min-h-0">
      <div
        ref={containerRef}
        className="h-full overflow-y-auto"
      >
        <div className="max-w-3xl mx-auto py-4">
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              onRegenerate={onRegenerate}
            />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>
      {showScrollDown && (
        <Button
          variant="outline"
          size="icon"
          className="btn-icon absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full shadow-md z-10"
          onClick={scrollToBottom}
          aria-label="回到底部"
        >
          <ArrowDown className="size-4" />
        </Button>
      )}
    </div>
  );
}
