"use client";

import { useState, useEffect, useRef } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface StreamingTextProps {
  content: string;
  streaming?: boolean;
  className?: string;
}

const BASE_DELAY = 20;
const DELAY_VARIANCE = 5;

export function StreamingText({
  content,
  streaming = false,
  className,
}: StreamingTextProps) {
  const [displayedContent, setDisplayedContent] = useState("");
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const contentRef = useRef("");
  const displayedLengthRef = useRef(0);

  useEffect(() => {
    if (!streaming) {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      contentRef.current = "";
      displayedLengthRef.current = 0;
      return;
    }

    contentRef.current = content;

    const typeNextChar = () => {
      if (displayedLengthRef.current >= contentRef.current.length) {
        timeoutRef.current = null;
        return;
      }

      displayedLengthRef.current += 1;
      setDisplayedContent(contentRef.current.slice(0, displayedLengthRef.current));

      if (displayedLengthRef.current < contentRef.current.length) {
        const delay = BASE_DELAY + (Math.random() * 2 - 1) * DELAY_VARIANCE;
        timeoutRef.current = setTimeout(typeNextChar, delay);
      } else {
        timeoutRef.current = null;
      }
    };

    if (!timeoutRef.current && displayedLengthRef.current < content.length) {
      const delay = BASE_DELAY + (Math.random() * 2 - 1) * DELAY_VARIANCE;
      timeoutRef.current = setTimeout(typeNextChar, delay);
    }
  }, [content, streaming]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  if (!streaming) {
    return <span className={cn("whitespace-pre-wrap", className)}>{content}</span>;
  }

  if (!displayedContent) {
    return (
      <span className={cn("inline-flex items-center", className)}>
        <Loader2 className="size-4 animate-spin text-muted-foreground" />
      </span>
    );
  }

  return (
    <span className={cn("whitespace-pre-wrap", className)}>
      {displayedContent}
      <span className="typing-cursor" aria-hidden />
    </span>
  );
}
