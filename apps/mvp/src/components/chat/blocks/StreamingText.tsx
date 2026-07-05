"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface StreamingTextProps {
  content: string;
  streaming?: boolean;
  className?: string;
}

export function StreamingText({
  content,
  streaming = false,
  className,
}: StreamingTextProps) {
  const [displayed, setDisplayed] = useState<string>("");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!streaming) return;
    if (timerRef.current) clearInterval(timerRef.current);
    let idx = displayed.length;
    if (idx >= content.length) return;
    timerRef.current = setInterval(() => {
      idx += 1;
      if (idx >= content.length) {
        setDisplayed(content);
        if (timerRef.current) clearInterval(timerRef.current);
      } else {
        setDisplayed(content.slice(0, idx));
      }
    }, 30);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content, streaming]);

  if (!streaming) {
    return <span className={cn("whitespace-pre-wrap", className)}>{content}</span>;
  }

  if (!displayed) {
    return (
      <span className={cn("inline-flex items-center", className)}>
        <Loader2 className="size-4 animate-spin text-muted-foreground" />
      </span>
    );
  }

  return (
    <span className={cn("whitespace-pre-wrap", className)}>
      {displayed}
      <span className="typing-cursor" aria-hidden />
    </span>
  );
}
