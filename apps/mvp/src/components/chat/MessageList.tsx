"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { ArrowDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import { MessageBubble } from "./MessageBubble";
import type { Message } from "@/types";

interface MessageListProps {
  messages: Message[];
  onRegenerate?: (id: string) => void;
  onCopy?: (id: string) => void;
  onShare?: (id: string) => void;
  onDelete?: (id: string) => void;
  onEdit?: (id: string) => void;
}

export function MessageList({
  messages,
  onRegenerate,
  onCopy,
  onShare,
  onDelete,
  onEdit,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [showScrollDown, setShowScrollDown] = useState(false);
  const seniorMode = useAppStore((state) => state.seniorMode);
  const autoScrollEnabledRef = useRef(true);
  const isUserScrollingRef = useRef(false);

  const scrollToBottom = useCallback((smooth = true) => {
    if (containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: smooth ? "smooth" : "auto",
      });
    }
  }, []);

  const isNearBottom = useCallback((threshold = 100) => {
    const el = containerRef.current;
    if (!el) return true;
    const { scrollTop, scrollHeight, clientHeight } = el;
    return scrollHeight - scrollTop - clientHeight < threshold;
  }, []);

  useEffect(() => {
    if (autoScrollEnabledRef.current) {
      requestAnimationFrame(() => {
        scrollToBottom(true);
      });
    }
  }, [messages, scrollToBottom]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let scrollTimeout: ReturnType<typeof setTimeout>;

    const handleScroll = () => {
      if (isUserScrollingRef.current) {
        const nearBottom = isNearBottom(150);
        if (nearBottom) {
          autoScrollEnabledRef.current = true;
          setShowScrollDown(false);
        } else {
          autoScrollEnabledRef.current = false;
          setShowScrollDown(true);
        }
      }
    };

    const handleWheel = () => {
      isUserScrollingRef.current = true;
      clearTimeout(scrollTimeout);
      scrollTimeout = setTimeout(() => {
        isUserScrollingRef.current = false;
      }, 150);
    };

    const handleTouchStart = () => {
      isUserScrollingRef.current = true;
    };

    const handleTouchEnd = () => {
      clearTimeout(scrollTimeout);
      scrollTimeout = setTimeout(() => {
        isUserScrollingRef.current = false;
        if (isNearBottom(150)) {
          autoScrollEnabledRef.current = true;
          setShowScrollDown(false);
        }
      }, 150);
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    el.addEventListener("wheel", handleWheel, { passive: true });
    el.addEventListener("touchstart", handleTouchStart, { passive: true });
    el.addEventListener("touchend", handleTouchEnd, { passive: true });

    return () => {
      el.removeEventListener("scroll", handleScroll);
      el.removeEventListener("wheel", handleWheel);
      el.removeEventListener("touchstart", handleTouchStart);
      el.removeEventListener("touchend", handleTouchEnd);
      clearTimeout(scrollTimeout);
    };
  }, [isNearBottom]);

  const handleScrollToBottom = () => {
    autoScrollEnabledRef.current = true;
    setShowScrollDown(false);
    scrollToBottom(true);
  };

  const lastMessageId = messages.length > 0 ? messages[messages.length - 1]?.id : null;

  return (
    <div className="relative flex-1 min-h-0">
      <div
        ref={containerRef}
        className="h-full overflow-y-auto"
      >
        <div className="max-w-3xl mx-auto py-4">
          {messages.map((msg) => {
            const isLast = msg.id === lastMessageId && msg.role === 'assistant';
            return (
              <MessageBubble
                key={msg.id}
                message={msg}
                onRegenerate={onRegenerate}
                onCopy={onCopy}
                onShare={onShare}
                onDelete={onDelete}
                onEdit={onEdit}
                isLastMessage={isLast}
              />
            );
          })}
          <div ref={bottomRef} />
        </div>
      </div>
      {showScrollDown && (
        <Button
          variant="outline"
          size={seniorMode ? "default" : "icon"}
          className={cn(
            "btn-icon absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full shadow-md z-10",
            seniorMode && "min-h-12 gap-2 px-4 text-base"
          )}
          onClick={handleScrollToBottom}
          aria-label="回到底部"
        >
          <ArrowDown className="size-4" />
          {seniorMode && <span>回到底部</span>}
        </Button>
      )}
    </div>
  );
}
