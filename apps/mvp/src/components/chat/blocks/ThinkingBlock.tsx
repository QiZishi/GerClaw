"use client";

import { useState } from "react";
import { Brain, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ThinkingBlock as ThinkingBlockData } from "@/types";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { projectPublicAnalysis } from "./public-execution-projection";

interface ThinkingBlockProps {
  data: ThinkingBlockData;
}

export function ThinkingBlock({ data }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(false);
  const reducedMotion = useReducedMotion();
  const isThinking = data.status === "thinking";
  const projection = projectPublicAnalysis(data);

  if (isThinking && !projection.detail) {
    // The message-level status bar owns the single animated indicator and
    // elapsed clock, so nested blocks never create a distracting loader wall.
    return null;
  }

  return (
    <div className="rounded-xl border border-border/40 bg-muted/30 overflow-hidden mb-2">
      <button
        type="button"
        onClick={() => projection.expandable && setExpanded((v) => !v)}
        className={cn(
          "senior-min-target flex w-full items-center justify-between gap-2 px-3 py-2 text-left",
          projection.expandable && "hover:bg-muted/50 transition-colors"
        )}
        aria-expanded={projection.expandable ? expanded : false}
        disabled={!projection.expandable}
      >
        <span className="flex items-center gap-2 text-sm text-muted-foreground/80">
          <Brain 
            className={cn(
              "size-4 shrink-0",
              isThinking && "text-primary"
            )} 
          />
          <span className="font-medium">
            {isThinking && expanded ? "收起分析" : projection.label}
          </span>
        </span>
        {projection.expandable && (
          <ChevronDown
            className={cn(
              "size-4 shrink-0 text-muted-foreground/60",
              reducedMotion ? "" : "transition-transform duration-200 ease-out",
              expanded && "rotate-180"
            )}
          />
        )}
      </button>
      {projection.expandable && projection.detail && (
        <div
          className={cn(
            "grid",
            reducedMotion ? "" : "transition-[grid-template-rows] duration-200 ease-out",
            expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
          )}
        >
          <div className="min-h-0 overflow-hidden">
            <div className="px-3 pb-3 pt-1 text-sm text-muted-foreground/80 whitespace-pre-wrap border-t border-border/30 leading-relaxed">
              {projection.detail}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
