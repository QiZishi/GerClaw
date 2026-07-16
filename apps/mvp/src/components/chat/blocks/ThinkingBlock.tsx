"use client";

import { useState } from "react";
import { Brain, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ThinkingBlock as ThinkingBlockData } from "@/types";
import { useReducedMotion } from "@/hooks/useReducedMotion";

interface ThinkingBlockProps {
  data: ThinkingBlockData;
}

export function ThinkingBlock({ data }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(false);
  const reducedMotion = useReducedMotion();
  const isThinking = data.status === "thinking";
  const hasContent = data.content.length > 0;

  if (isThinking && !hasContent) {
    // The message-level status bar owns the single animated indicator and
    // elapsed clock, so nested blocks never create a distracting loader wall.
    return null;
  }

  return (
    <div className="rounded-xl border border-border/40 bg-muted/30 overflow-hidden mb-2">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-muted/50 transition-colors"
        aria-expanded={expanded}
      >
        <span className="flex items-center gap-2 text-sm text-muted-foreground/80">
          <Brain 
            className={cn(
              "size-4 shrink-0",
              isThinking && "text-primary"
            )} 
          />
          <span className="font-medium">
            {isThinking ? "思考中" : expanded ? "收起思考" : "已思考"}
          </span>
        </span>
        {hasContent && (
          <ChevronDown
            className={cn(
              "size-4 shrink-0 text-muted-foreground/60",
              reducedMotion ? "" : "transition-transform duration-200 ease-out",
              expanded && "rotate-180"
            )}
          />
        )}
      </button>
      {hasContent && (
        <div
          className={cn(
            "grid",
            reducedMotion ? "" : "transition-[grid-template-rows] duration-200 ease-out",
            expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
          )}
        >
          <div className="min-h-0 overflow-hidden">
            <div className="px-3 pb-3 pt-1 text-sm text-muted-foreground/80 whitespace-pre-wrap border-t border-border/30 leading-relaxed">
              {data.content}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
