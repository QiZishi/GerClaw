"use client";

import { useState } from "react";
import { Brain, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ThinkingBlock as ThinkingBlockData } from "@/types";
import { formatDuration } from "@/lib/format";

interface ThinkingBlockProps {
  data: ThinkingBlockData;
}

/**
 * §4.2.3 思考过程块
 * 默认折叠，思考中状态显示脉冲点动画，点击展开查看完整推理过程
 */
export function ThinkingBlock({ data }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(false);
  const isThinking = data.status === "thinking";
  const duration =
    data.endedAt && data.startedAt
      ? data.endedAt - data.startedAt
      : undefined;

  return (
    <div className="rounded-lg border border-border bg-muted/50 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-muted/70 transition-colors"
        aria-expanded={expanded}
      >
        <span className="flex items-center gap-2 text-sm text-muted-foreground">
          <Brain className="size-4 shrink-0" />
          <span className="font-medium">
            {isThinking ? "思考中" : "思考过程"}
          </span>
          {isThinking && (
            <span className="flex items-center" aria-label="正在思考">
              <span className="thinking-dot" />
              <span className="thinking-dot" />
              <span className="thinking-dot" />
            </span>
          )}
          {!isThinking && duration !== undefined && (
            <span className="text-xs text-muted-foreground/70">
              · {formatDuration(duration)}
            </span>
          )}
        </span>
        <ChevronDown
          className={cn(
            "size-4 shrink-0 text-muted-foreground transition-transform",
            expanded && "rotate-180"
          )}
        />
      </button>
      {expanded && (
        <div className="px-3 pb-3 pt-1 text-sm text-muted-foreground whitespace-pre-wrap border-t border-border/60">
          {data.content}
        </div>
      )}
    </div>
  );
}
