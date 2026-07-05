"use client";

import { Check, FileText, RotateCw, X } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { formatFileSize } from "@/lib/format";
import type { FileTag as FileTagData } from "@/types";

interface FileTagProps {
  data: FileTagData;
  onRemove?: (id: string) => void;
  onRetry?: (id: string) => void;
  onClick?: (id: string) => void;
}

/**
 * §4.2.3 文件标签
 * 显示：文件名 + 类型图标 + 大小 + 状态（uploading/parsing/done/failed）+ × 移除
 * uploading/parsing 显示进度条
 */
export function FileTag({ data, onRemove, onRetry, onClick }: FileTagProps) {
  const statusText = () => {
    switch (data.status) {
      case "uploading":
        return "上传中…";
      case "parsing":
        return "解析中…";
      case "done":
        return "已就绪";
      case "failed":
        return "解析失败";
    }
  };

  const statusColor = () => {
    switch (data.status) {
      case "done":
        return "text-green-600";
      case "failed":
        return "text-destructive";
      default:
        return "text-muted-foreground";
    }
  };

  return (
    <div
      className={cn(
        "inline-flex flex-col gap-1 rounded-lg border border-border bg-muted/40 px-3 py-2 min-w-[200px]",
        onClick && "cursor-pointer hover:bg-muted/70 transition-colors"
      )}
      onClick={onClick ? () => onClick(data.id) : undefined}
    >
      <div className="flex items-center gap-2">
        <FileText className="size-4 shrink-0 text-muted-foreground" />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">{data.fileName}</div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>{formatFileSize(data.fileSize)}</span>
            <span>·</span>
            <span className={statusColor()}>{statusText()}</span>
          </div>
        </div>
        {data.status === "done" && (
          <Check className="size-4 text-green-600 shrink-0" />
        )}
        {data.status === "failed" && onRetry && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onRetry(data.id);
            }}
            className="text-muted-foreground hover:text-foreground shrink-0"
            aria-label="重试"
          >
            <RotateCw className="size-3.5" />
          </button>
        )}
        {onRemove && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onRemove(data.id);
            }}
            className="text-muted-foreground hover:text-destructive shrink-0"
            aria-label="移除"
          >
            <X className="size-3.5" />
          </button>
        )}
      </div>
      {(data.status === "uploading" || data.status === "parsing") && (
        <Progress value={data.progress ?? 0} className="h-1" />
      )}
      {data.status === "failed" && data.errorMessage && (
        <div className="text-xs text-destructive">{data.errorMessage}</div>
      )}
    </div>
  );
}
