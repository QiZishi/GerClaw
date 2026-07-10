"use client";

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

export function StreamingText({
  content,
  streaming = false,
  className,
  citations,
  showPlaceholder = true,
}: StreamingTextProps) {
  if (!content) {
    if (!streaming || !showPlaceholder) {
      return null;
    }
    return (
      <div className={cn("inline-flex items-center gap-[3px] h-5 text-muted-foreground/60", className)}>
        <span className="typing-dot" style={{ animationDelay: "-0.32s" }} />
        <span className="typing-dot" style={{ animationDelay: "-0.16s" }} />
        <span className="typing-dot" />
      </div>
    );
  }

  return (
    <div className={cn("relative", className)}>
      <MarkdownRenderer content={content} citations={citations} />
      {streaming && <span className="typing-cursor" aria-hidden />}
    </div>
  );
}
