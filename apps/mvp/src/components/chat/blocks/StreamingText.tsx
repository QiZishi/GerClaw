"use client";

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
  if (!streaming) {
    return <span className={cn("whitespace-pre-wrap", className)}>{content}</span>;
  }

  if (!content) {
    return (
      <span className={cn("inline-flex items-center", className)}>
        <Loader2 className="size-4 animate-spin text-muted-foreground" />
      </span>
    );
  }

  return (
    <span className={cn("whitespace-pre-wrap", className)}>
      {content}
      <span className="typing-cursor" aria-hidden />
    </span>
  );
}
