"use client";

import { Check, FileText, RotateCw, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatFileSize } from "@/lib/format";
import { useAppStore } from "@/stores/appStore";
import type { FileTag as FileTagData } from "@/types";

interface FileTagProps {
  data: FileTagData;
  onRemove?: (id: string) => void;
  onRetry?: (id: string) => void;
  onCancel?: (id: string) => void;
  onClick?: (id: string) => void;
}

/**
 * §4.2.3 文件标签
 * 显示：文件名 + 类型图标 + 大小 + 状态（uploading/parsing/done/failed）+ × 移除
 * MinerU 是单次 BFF 请求，浏览器没有真实可观测的上传/解析百分比；解析中仅显示稳定文字，避免伪进度。
 */
export function FileTag({ data, onRemove, onRetry, onCancel, onClick }: FileTagProps) {
  const role = useAppStore((state) => state.role);
  const seniorMode = useAppStore((state) => state.seniorMode);
  const isSeniorPatient = role === "patient" && seniorMode;
  const statusText = () => {
    switch (data.status) {
      case "uploading":
        return "正在提交文档";
      case "parsing":
        return "正在解析文档";
      case "done":
        return data.serverDocumentId ? "已加入本次对话" : "请提问后发送";
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
        onClick && "cursor-pointer hover:bg-muted/70 transition-colors",
        isSeniorPatient && "min-h-16 gap-2 px-4 py-3"
      )}
      onClick={onClick ? () => onClick(data.id) : undefined}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onClick(data.id);
              }
            }
          : undefined
      }
    >
      <div className="flex items-center gap-2">
        <FileText className="size-4 shrink-0 text-muted-foreground" />
        <div className="flex-1 min-w-0">
          <div className={cn("text-sm font-medium truncate", isSeniorPatient && "text-lg")}>{data.fileName}</div>
          <div className={cn("flex items-center gap-2 text-xs text-muted-foreground", isSeniorPatient && "text-lg")}>
            <span>{formatFileSize(data.fileSize)}</span>
            <span>·</span>
            <span className={statusColor()} role="status" aria-live="polite">
              {statusText()}
            </span>
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
            className={cn(
              "text-muted-foreground hover:text-foreground shrink-0",
              isSeniorPatient && "inline-flex min-h-12 items-center gap-1 px-2 text-base"
            )}
            aria-label="重试"
          >
            <RotateCw className="size-3.5" />
            {isSeniorPatient && <span>重试</span>}
          </button>
        )}
        {data.status === "parsing" && onCancel && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onCancel(data.id);
            }}
            className={cn(
              "shrink-0 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline",
              isSeniorPatient && "inline-flex min-h-12 items-center px-2 text-base"
            )}
          >
            取消解析
          </button>
        )}
        {onRemove && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onRemove(data.id);
            }}
            className={cn(
              "text-muted-foreground hover:text-destructive shrink-0",
              isSeniorPatient && "inline-flex min-h-12 items-center gap-1 px-2 text-base"
            )}
            aria-label="移除"
          >
            <X className="size-3.5" />
            {isSeniorPatient && <span>移除</span>}
          </button>
        )}
      </div>
      {data.status === "failed" && data.errorMessage && (
        <div className={cn("text-xs text-destructive", isSeniorPatient && "text-base")}>{data.errorMessage}</div>
      )}
    </div>
  );
}
