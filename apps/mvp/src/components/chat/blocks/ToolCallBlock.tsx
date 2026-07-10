"use client";

import { useState } from "react";
import { Check, ChevronDown, Loader2, RotateCw, Search, Wrench, X, AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatDuration } from "@/lib/format";
import type { ToolCallBlock as ToolCallBlockData, SearchResultItem } from "@/types";
import { useReducedMotion } from "@/hooks/useReducedMotion";

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
  const reducedMotion = useReducedMotion();
  const isRunning = data.status === "running";
  const isDone = data.status === "done";
  const isFailed = data.status === "failed";
  const isSearch = isWebSearch(data.toolName);
  const hasContent = (data.params && Object.keys(data.params).length > 0) || data.result !== undefined;

  const displayName = getToolDisplayName(data.toolName);
  const searchQuery = isSearch ? getSearchQuery(data) : "";
  const resultCount = isSearch ? getSearchResultCount(data) : 0;

  const results: SearchResultItem[] | null = isSearch && isDone && data.result
    ? (typeof data.result === "object" && "results" in (data.result as object)
      ? (data.result as { results: SearchResultItem[] }).results
      : null)
    : null;
  const hasSearchResults = results !== null && Array.isArray(results) && results.length > 0;

  const expandTransition = reducedMotion ? "" : "transition-[grid-template-rows] duration-200 ease-out";
  const chevronTransition = reducedMotion ? "" : "transition-transform duration-200 ease-out";

  const toolIconEl = isRunning ? (
    <Loader2 className="size-4 shrink-0 animate-spin" />
  ) : isSearch ? (
    <Search className="size-4 shrink-0" />
  ) : (
    <Wrench className="size-4 shrink-0" />
  );

  const shouldShowExpandButton = isSearch ? (isDone && results !== null) : hasContent;
  const shouldShowExpandContent = isSearch ? (isDone && results !== null) : hasContent;

  if (isSearch) {
    return (
      <div className="rounded-xl border border-border/40 bg-muted/30 overflow-hidden mb-2">
        <div
          className={cn(
            "flex w-full items-center justify-between gap-2 px-3 py-2",
            shouldShowExpandButton && "cursor-pointer hover:bg-muted/50 transition-colors"
          )}
          onClick={() => shouldShowExpandButton && setExpanded((v) => !v)}
        >
          <span className="flex items-center gap-2 text-sm text-muted-foreground/80 min-w-0">
            {toolIconEl}
            <span className="font-medium shrink-0">{displayName}</span>
            {isRunning && searchQuery ? (
              <span className="truncate text-foreground/80">
                正在搜索「{searchQuery}」...
              </span>
            ) : isDone && searchQuery ? (
              <span className="truncate text-foreground/80">
                🔍 「{searchQuery}」· {hasSearchResults ? `已找到 ${resultCount} 个结果` : "已完成"}
              </span>
            ) : isFailed ? (
              <span className="flex items-center gap-1 text-destructive truncate">
                <AlertTriangle className="size-3.5 shrink-0" />
                搜索失败{data.errorMessage ? `：${data.errorMessage}` : ""}
              </span>
            ) : searchQuery ? (
              <span className="truncate">「{searchQuery}」</span>
            ) : null}
          </span>
          <span className="flex items-center gap-1 shrink-0">
            <StatusBadge status={data.status} />
            {isFailed && onRetry && (
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
            {shouldShowExpandButton && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setExpanded((v) => !v);
                }}
                className="p-1 hover:bg-muted/50 rounded transition-colors"
                aria-expanded={expanded}
                aria-label={expanded ? "收起详情" : "展开详情"}
              >
                <ChevronDown
                  className={cn(
                    "size-3.5 text-muted-foreground/60",
                    chevronTransition,
                    expanded && "rotate-180"
                  )}
                />
              </button>
            )}
          </span>
        </div>
        {shouldShowExpandContent && (
          <div
            className={cn(
              "grid",
              expandTransition,
              expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
            )}
            aria-hidden={!expanded}
          >
            <div className="overflow-hidden">
              {hasSearchResults ? (
                <div className="border-t border-border/30 max-h-80 overflow-y-auto">
                  {results.map((item, index) => (
                    <div
                      key={item.id || index}
                      className={cn(
                        "px-3 py-2",
                        index > 0 && "border-t border-border/30"
                      )}
                    >
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 dark:text-blue-400 hover:underline font-medium text-sm block"
                      >
                        {item.title}
                      </a>
                      <div className="text-xs text-muted-foreground/60 mt-0.5">
                        {item.source}
                        {item.publishedDate && ` · ${item.publishedDate}`}
                      </div>
                      <p className="text-xs text-muted-foreground/80 mt-1 line-clamp-2">
                        {item.snippet}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="border-t border-border/30 px-3 py-2 text-sm text-muted-foreground/80">
                  搜索完成
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    );
  }

  // 其他工具：保持原有可展开样式
  return (
    <div className="rounded-xl border border-border/40 bg-muted/30 overflow-hidden mb-2">
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
              "size-4 shrink-0 text-muted-foreground/60",
              chevronTransition,
              expanded && "rotate-180"
            )}
          />
        )}
      </button>
      {hasContent && (
        <div
          className={cn(
            "grid",
            expandTransition,
            expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
          )}
          aria-hidden={!expanded}
        >
          <div className="overflow-hidden">
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
          </div>
        </div>
      )}
    </div>
  );
}
