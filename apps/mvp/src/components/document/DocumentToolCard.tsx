"use client";

import { useState } from "react";
import {
  Check,
  ChevronDown,
  FileText,
  Loader2,
  RotateCw,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatFileSize } from "@/lib/format";
import type { FileTag as FileTagData } from "@/types";

interface DocumentToolCardProps {
  data: FileTagData;
  onRetry?: (id: string) => void;
}

/**
 * §4.2.3 文档解析工具卡片
 * 类似 ToolCallBlock，但专门用于文档解析
 * 显示：文档名 + 大小 + 解析状态 + 解析结果（parsedMarkdown）
 */
export function DocumentToolCard({ data, onRetry }: DocumentToolCardProps) {
  const [expanded, setExpanded] = useState(false);

  const statusBadge = () => {
    switch (data.status) {
      case "uploading":
        return (
          <Badge variant="secondary" className="gap-1 text-blue-600">
            <Loader2 className="size-3 animate-spin" />
            上传中
          </Badge>
        );
      case "parsing":
        return (
          <Badge variant="secondary" className="gap-1 text-blue-600">
            <Loader2 className="size-3 animate-spin" />
            解析中
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
          <FileText className="size-4 shrink-0 text-muted-foreground" />
          <span className="text-sm font-medium truncate">{data.fileName}</span>
          <span className="text-xs text-muted-foreground shrink-0">
            {formatFileSize(data.fileSize)}
          </span>
          {statusBadge()}
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
          {data.parsedMarkdown ? (
            <div>
              <div className="text-muted-foreground mb-1">解析结果</div>
              <pre className="bg-muted rounded p-2 overflow-x-auto font-mono text-xs whitespace-pre-wrap">
                {data.parsedMarkdown}
              </pre>
            </div>
          ) : (
            <div className="text-muted-foreground">
              {data.status === "failed"
                ? data.errorMessage ?? "解析失败"
                : "暂无解析结果"}
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
