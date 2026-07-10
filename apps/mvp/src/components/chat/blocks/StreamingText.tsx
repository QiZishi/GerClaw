"use client";

import { useState, useEffect, useRef } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { MarkdownRenderer } from "../MarkdownRenderer";
import type { Citation } from "@/types";

interface StreamingTextProps {
  content: string;
  streaming?: boolean;
  className?: string;
  citations?: Citation[];
}

const BASE_DELAY = 20;
const DELAY_VARIANCE = 5;

function StreamingTextInner({
  content,
  className,
  citations,
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
    return (
      <span className={cn("inline-flex items-center", className)}>
        <Loader2 className="size-4 animate-spin text-muted-foreground" />
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
    />
  );
}
