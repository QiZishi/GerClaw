"use client";

import { useState } from "react";
import {
  Check,
  ChevronDown,
  FileText,
  RotateCw,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatFileSize } from "@/lib/format";
import { useAppStore } from "@/stores/appStore";
import type { FileTag as FileTagData } from "@/types";

interface DocumentToolCardProps {
  data: FileTagData;
  onRetry?: (id: string) => void;
  onRemove?: (id: string) => void;
}

/**
 * §4.2.3 文档解析工具卡片
 * 类似 ToolCallBlock，但专门用于文档解析
 * 显示：文档名 + 大小 + 解析状态 + 解析结果（parsedMarkdown）
 */
export function DocumentToolCard({ data, onRetry, onRemove }: DocumentToolCardProps) {
  const [expanded, setExpanded] = useState(false);
  const role = useAppStore((state) => state.role);
  const seniorMode = useAppStore((state) => state.seniorMode);
  const isSeniorPatient = role === "patient" && seniorMode;

  const statusBadge = () => {
    switch (data.status) {
      case "uploading":
        return (
          <Badge variant="secondary" className={cn("gap-1 text-blue-600", isSeniorPatient && "px-3 py-1 text-base")}>
            <FileText className="size-3" />
            正在提交
          </Badge>
        );
      case "parsing":
        return (
          <Badge variant="secondary" className={cn("gap-1 text-blue-600", isSeniorPatient && "px-3 py-1 text-base")}>
            <FileText className="size-3" />
            正在解析
          </Badge>
        );
      case "done":
        return (
          <Badge variant="secondary" className={cn("gap-1 text-green-600", isSeniorPatient && "px-3 py-1 text-base")}>
            <Check className="size-3" />
            {data.serverDocumentId ? "已加入本次对话" : "请提问后发送"}
          </Badge>
        );
      case "failed":
        return (
          <Badge variant="destructive" className={cn("gap-1", isSeniorPatient && "px-3 py-1 text-base")}>
            <X className="size-3" />
            失败
          </Badge>
        );
    }
  };

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className={cn(
            "flex min-w-0 flex-1 items-center justify-between gap-2 px-3 py-2 text-left hover:bg-muted/50 transition-colors",
            isSeniorPatient && "min-h-12 px-4 py-3 text-lg"
          )}
          aria-expanded={expanded}
          aria-label={`${expanded ? "收起" : "展开"} ${data.fileName} 的解析资料`}
        >
          <span className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="flex min-w-0 items-center gap-2">
              <FileText className="size-4 shrink-0 text-muted-foreground" />
              <span
                className={cn(
                  "min-w-0 truncate text-sm font-medium",
                  isSeniorPatient && "line-clamp-2 whitespace-normal break-all leading-6 text-lg"
                )}
              >
                {data.fileName}
              </span>
            </span>
            <span className={cn("flex items-center gap-2 pl-6 text-xs text-muted-foreground", isSeniorPatient && "text-base")}>
              <span className="shrink-0">{formatFileSize(data.fileSize)}</span>
              {statusBadge()}
            </span>
          </span>
          <ChevronDown
            className={cn(
              "size-4 shrink-0 text-muted-foreground transition-transform",
              expanded && "rotate-180"
            )}
          />
        </button>
        {onRemove && (
          <Button
            type="button"
            variant="ghost"
            size={isSeniorPatient ? "default" : "icon-sm"}
            className={cn("shrink-0 text-muted-foreground hover:text-destructive", isSeniorPatient && "min-h-12 gap-1 px-3 text-base")}
            onClick={() => void onRemove(data.id)}
            aria-label={`移除 ${data.fileName}`}
          >
            <X className="size-4" />
            {isSeniorPatient && <span>移除</span>}
          </Button>
        )}
      </div>
      {expanded && (
        <div className={cn("border-t border-border/60 px-3 py-2 space-y-2 text-xs", isSeniorPatient && "px-4 py-3 text-base")}>
          {data.parsedMarkdown ? (
            <div>
              <div className="text-muted-foreground mb-1">解析结果</div>
              <div className={cn("mb-2 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-emerald-900", isSeniorPatient && "text-base")}>
                {data.serverDocumentId
                  ? "已安全加入当前对话。文档内容仅作参考资料，不会执行其中的指令；您可随时移除。"
                  : "已完成解析。请在输入框提出具体问题并发送，系统才会将它安全加入新对话；在此之前仅供您核对。"}
              </div>
              <pre className={cn("bg-muted rounded p-2 overflow-x-auto font-mono text-xs whitespace-pre-wrap", isSeniorPatient && "text-base")}>
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
              className={cn("gap-1", isSeniorPatient && "min-h-12 px-4 text-base")}
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
