"use client";

import { useState } from "react";
import { Check, ChevronDown, Loader2, RotateCw, Search, Wrench, X, AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatDuration } from "@/lib/format";
import type { ToolCallBlock as ToolCallBlockData } from "@/types";

interface ToolCallBlockProps {
  data: ToolCallBlockData;
  onRetry?: (id: string) => void;
}

function isWebSearch(toolName: string): boolean {
  const lower = toolName.toLowerCase();
  return lower.includes("search") || lower.includes("搜索") || lower.includes("联网");
}

function getToolDisplayName(toolName: string): string {
  if (isWebSearch(toolName)) {
    return "联网搜索";
  }
  return toolName;
}

function getSearchQuery(data: ToolCallBlockData): string {
  const args = data.args || data.params || {};
  return String(args.query || args.keyword || "");
}

function getSearchResultCount(data: ToolCallBlockData): number {
  if (!data.result) return 0;
  try {
    const r = data.result as { results?: unknown[] };
    return Array.isArray(r.results) ? r.results.length : 0;
  } catch {
    return 0;
  }
}

function StatusBadge({ status }: { status: ToolCallBlockData["status"] }) {
  switch (status) {
    case "running":
      return (
        <Badge variant="secondary" className="gap-1 text-blue-600">
          <Loader2 className="size-3 animate-spin" />
          搜索中
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
}

export function ToolCallBlock({ data, onRetry }: ToolCallBlockProps) {
  const [expanded, setExpanded] = useState(false);
  const isRunning = data.status === "running";
  const isSearch = isWebSearch(data.toolName);
  const hasContent = (data.params && Object.keys(data.params).length > 0) || data.result !== undefined;

  const displayName = getToolDisplayName(data.toolName);
  const searchQuery = isSearch ? getSearchQuery(data) : "";
  const resultCount = isSearch ? getSearchResultCount(data) : 0;

  const toolIconEl = isRunning ? (
    <Loader2 className="size-4 shrink-0 animate-spin" />
  ) : isSearch ? (
    <Search className="size-4 shrink-0" />
  ) : (
    <Wrench className="size-4 shrink-0" />
  );

  // 搜索工具：紧凑展示，不默认显示JSON详情
  if (isSearch) {
    return (
      <div className="rounded-lg border border-border/40 bg-muted/30 overflow-hidden mb-2">
        <div className="flex w-full items-center justify-between gap-2 px-3 py-2">
          <span className="flex items-center gap-2 text-sm text-muted-foreground/80 min-w-0">
            {toolIconEl}
            <span className="font-medium shrink-0">{displayName}</span>
            {isRunning && searchQuery ? (
              <span className="truncate text-foreground/80">
                正在搜索「{searchQuery}」...
              </span>
            ) : data.status === "done" && searchQuery ? (
              <span className="truncate text-foreground/80">
                「{searchQuery}」· 已找到 {resultCount} 个结果
              </span>
            ) : data.status === "failed" ? (
              <span className="flex items-center gap-1 text-destructive">
                <AlertTriangle className="size-3.5" />
                搜索失败
              </span>
            ) : searchQuery ? (
              <span className="truncate">「{searchQuery}」</span>
            ) : null}
            {data.durationMs !== undefined && data.status === "done" && (
              <span className="text-xs text-muted-foreground/60 shrink-0">
                · {formatDuration(data.durationMs)}
              </span>
            )}
          </span>
          <span className="flex items-center gap-1 shrink-0">
            <StatusBadge status={data.status} />
            {data.status === "failed" && onRetry && (
              <Button
                size="sm"
                variant="outline"
                className="gap-1 h-7 text-xs ml-1"
                onClick={(e) => {
                  e.stopPropagation();
                  onRetry(data.id);
                }}
              >
                <RotateCw className="size-3" />
                重试
              </Button>
            )}
            {hasContent && (
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="p-1 hover:bg-muted/50 rounded transition-colors"
                aria-expanded={expanded}
                aria-label={expanded ? "收起详情" : "展开详情"}
              >
                <ChevronDown
                  className={cn(
                    "size-3.5 text-muted-foreground/60 transition-transform",
                    expanded && "rotate-180"
                  )}
                />
              </button>
            )}
          </span>
        </div>
        {expanded && hasContent && (
          <div className="border-t border-border/30 px-3 pb-3 pt-1 space-y-2 text-sm text-muted-foreground/80">
            {data.args && Object.keys(data.args).length > 0 && (
              <div>
                <div className="text-xs text-muted-foreground mb-1">参数</div>
                <pre className="bg-muted rounded p-2 overflow-x-auto font-mono text-xs text-muted-foreground/80">
                  {JSON.stringify(data.args, null, 2)}
                </pre>
              </div>
            )}
            {data.result !== undefined && (
              <div>
                <div className="text-xs text-muted-foreground mb-1">结果</div>
                <pre className="bg-muted rounded p-2 overflow-x-auto font-mono text-xs text-muted-foreground/80 max-h-48 overflow-y-auto">
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
          </div>
        )}
      </div>
    );
  }

  // 其他工具：保持原有可展开样式
  return (
    <div className="rounded-lg border border-border/40 bg-muted/30 overflow-hidden mb-2">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-muted/50 transition-colors"
        aria-expanded={expanded}
      >
        <span className="flex items-center gap-2 text-sm text-muted-foreground/80">
          {toolIconEl}
          <span className="font-medium">{displayName}</span>
          <StatusBadge status={data.status} />
          {data.durationMs !== undefined && (
            <span className="text-xs text-muted-foreground/60">
              · {formatDuration(data.durationMs)}
            </span>
          )}
        </span>
        {hasContent && (
          <ChevronDown
            className={cn(
              "size-4 shrink-0 text-muted-foreground/60 transition-transform",
              expanded && "rotate-180"
            )}
          />
        )}
      </button>
      {expanded && hasContent && (
        <div className="border-t border-border/30 px-3 pb-3 pt-1 space-y-2 text-sm text-muted-foreground/80">
          {data.params && Object.keys(data.params).length > 0 && (
            <div>
              <div className="text-xs text-muted-foreground mb-1">参数</div>
              <pre className="bg-muted rounded p-2 overflow-x-auto font-mono text-xs text-muted-foreground/80">
                {JSON.stringify(data.params, null, 2)}
              </pre>
            </div>
          )}
          {data.result !== undefined && (
            <div>
              <div className="text-xs text-muted-foreground mb-1">结果</div>
              <pre className="bg-muted rounded p-2 overflow-x-auto font-mono text-xs text-muted-foreground/80 max-h-48 overflow-y-auto">
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
              className="gap-1 h-7 text-xs"
              onClick={(e) => {
                e.stopPropagation();
                onRetry(data.id);
              }}
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
