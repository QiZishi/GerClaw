"use client";

import { useState, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { MarkdownRenderer } from "../MarkdownRenderer";
import type { Citation } from "@/types";

interface StreamingTextProps {
  content: string;
  streaming?: boolean;
  className?: string;
  citations?: Citation[];
  showPlaceholder?: boolean;
}

const BASE_DELAY = 20;
const DELAY_VARIANCE = 5;

function StreamingTextInner({
  content,
  className,
  citations,
  showPlaceholder = true,
}: Omit<StreamingTextProps, "streaming">) {
  const [displayedLength, setDisplayedLength] = useState(0);
  const [showCursor, setShowCursor] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const targetLengthRef = useRef(0);
  const startedRef = useRef(false);

  useEffect(() => {
    targetLengthRef.current = content.length;

    if (!startedRef.current) {
      startedRef.current = true;
      setShowCursor(true);
      const delay = BASE_DELAY + (Math.random() * 2 - 1) * DELAY_VARIANCE;
      timeoutRef.current = setTimeout(function typeNext() {
        setDisplayedLength((prev) => {
          const next = prev + 1;
          if (next >= targetLengthRef.current) {
            setShowCursor(false);
            timeoutRef.current = null;
            return targetLengthRef.current;
          }
          const nextDelay = BASE_DELAY + (Math.random() * 2 - 1) * DELAY_VARIANCE;
          timeoutRef.current = setTimeout(typeNext, nextDelay);
          return next;
        });
      }, delay);
    }

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [content]);

  useEffect(() => {
    if (displayedLength < content.length && !timeoutRef.current) {
      setShowCursor(true);
      const delay = BASE_DELAY + (Math.random() * 2 - 1) * DELAY_VARIANCE;
      timeoutRef.current = setTimeout(function typeNext() {
        setDisplayedLength((prev) => {
          const next = prev + 1;
          if (next >= targetLengthRef.current) {
            setShowCursor(false);
            timeoutRef.current = null;
            return targetLengthRef.current;
          }
          const nextDelay = BASE_DELAY + (Math.random() * 2 - 1) * DELAY_VARIANCE;
          timeoutRef.current = setTimeout(typeNext, nextDelay);
          return next;
        });
      }, delay);
    }
  }, [content, displayedLength]);

  const displayedContent = content.slice(0, displayedLength);

  if (!displayedContent) {
    if (!showPlaceholder) {
      return null;
    }
    return (
      <span className={cn("inline-flex items-center gap-[3px] h-5 text-muted-foreground/60", className)}>
        <span className="typing-dot" style={{ animationDelay: "-0.32s" }} />
        <span className="typing-dot" style={{ animationDelay: "-0.16s" }} />
        <span className="typing-dot" />
      </span>
    );
  }

  return (
    <span className={cn("block relative", className)}>
      <MarkdownRenderer content={displayedContent} citations={citations} />
      {showCursor && <span className="typing-cursor" aria-hidden />}
    </span>
  );
}

export function StreamingText({
  content,
  streaming = false,
  className,
  citations,
  showPlaceholder = true,
}: StreamingTextProps) {
  if (!streaming) {
    return (
      <span className={cn("block", className)}>
        <MarkdownRenderer content={content} citations={citations} />
      </span>
    );
  }

  return (
    <StreamingTextInner
      content={content}
      className={className}
      citations={citations}
      showPlaceholder={showPlaceholder}
    />
  );
}
