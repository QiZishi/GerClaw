"use client";

import { useState } from "react";
import { Check, ChevronDown, Loader2, RotateCw, Wrench, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatDuration } from "@/lib/format";
import type { ToolCallBlock as ToolCallBlockData } from "@/types";

interface ToolCallBlockProps {
  data: ToolCallBlockData;
  onRetry?: (id: string) => void;
}

/**
 * §4.2.3 工具调用块
 * 三态：running / done / failed
 * 默认折叠，展开显示 JSON 参数 + 结果 + 耗时
 */
export function ToolCallBlock({ data, onRetry }: ToolCallBlockProps) {
  const [expanded, setExpanded] = useState(false);

  const statusBadge = () => {
    switch (data.status) {
      case "running":
        return (
          <Badge variant="secondary" className="gap-1 text-blue-600">
            <Loader2 className="size-3 animate-spin" />
            运行中
          </Badge>
        );
      case "done":
        return (
          <Badge variant="secondary" className="gap-1 text-green-600">
            <Check className="size-3" />
            完成
          </Badge>
        );
      case "failed":
        return (
          <Badge variant="destructive" className="gap-1">
            <X className="size-3" />
            失败
          </Badge>
        );
    }
  };

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-muted/50 transition-colors"
        aria-expanded={expanded}
      >
        <span className="flex items-center gap-2 min-w-0">
          <Wrench className="size-4 shrink-0 text-muted-foreground" />
          <span className="text-sm font-medium truncate">
            {data.toolName}
          </span>
          {statusBadge()}
          {data.durationMs !== undefined && (
            <span className="text-xs text-muted-foreground shrink-0">
              {formatDuration(data.durationMs)}
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
        <div className="border-t border-border/60 px-3 py-2 space-y-2 text-xs">
          <div>
            <div className="text-muted-foreground mb-1">参数</div>
            <pre className="bg-muted rounded p-2 overflow-x-auto font-mono text-xs">
              {JSON.stringify(data.params, null, 2)}
            </pre>
          </div>
          {data.result !== undefined && (
            <div>
              <div className="text-muted-foreground mb-1">结果</div>
              <pre className="bg-muted rounded p-2 overflow-x-auto font-mono text-xs">
                {typeof data.result === "string"
                  ? data.result
                  : JSON.stringify(data.result, null, 2)}
              </pre>
            </div>
          )}
          {data.status === "failed" && data.errorMessage && (
            <div className="text-destructive text-xs">
              错误：{data.errorMessage}
            </div>
          )}
          {data.status === "failed" && onRetry && (
            <Button
              size="sm"
              variant="outline"
              className="gap-1"
              onClick={() => onRetry(data.id)}
            >
              <RotateCw className="size-3" />
              重试
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
