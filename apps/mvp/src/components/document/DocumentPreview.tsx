"use client";

import { useState } from "react";
import {
  Copy,
  Check,
  ExternalLink,
  FileText,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";
import { useAppStore } from "@/stores/appStore";
import { formatFileSize, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { FileTag as FileTagData } from "@/types";

interface DocumentPreviewProps {
  file: FileTagData;
  className?: string;
}

/**
 * §文件预览 右侧动态面板
 * 显示文件元信息 + 解析后的 Markdown 内容
 * 支持复制原文 / 缩放字号
 */
export function DocumentPreview({ file, className }: DocumentPreviewProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const [copied, setCopied] = useState(false);
  const [zoom, setZoom] = useState(0); // -2 ~ +2
  // 解析时间在组件挂载时确定一次（避免渲染中调用 Date.now 不纯）
  const [parsedAt] = useState(() => Date.now());

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(file.parsedMarkdown ?? "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // 剪贴板 API 不可用 — 静默失败
    }
  };

  const zoomClass = [
    "text-xs",
    "text-sm",
    "text-base",
    "text-lg",
    "text-xl",
  ][Math.max(0, Math.min(4, zoom + 2))];

  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* 头部：文件元信息 */}
      <div className="px-3 py-2 border-b border-border space-y-1.5">
        <div className="flex items-start gap-2">
          <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
            <FileText className="size-4" />
          </div>
          <div className="flex-1 min-w-0">
            <div
              className={cn(
                "text-sm font-medium truncate",
                seniorMode && "text-base"
              )}
              title={file.fileName}
            >
              {file.fileName}
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
              <span>{formatFileSize(file.fileSize)}</span>
              <span>·</span>
              <span className="uppercase">{file.fileType}</span>
              <Badge
                variant={file.status === "done" ? "secondary" : "outline"}
                className="text-[10px] py-0"
              >
                {statusLabel(file.status)}
              </Badge>
            </div>
          </div>
        </div>
        <div className="flex items-center justify-end gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            className="btn-icon"
            onClick={() => setZoom((z) => Math.max(-2, z - 1))}
            disabled={zoom <= -2}
            aria-label="缩小字号"
          >
            <ZoomOut className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            className="btn-icon"
            onClick={() => setZoom((z) => Math.min(2, z + 1))}
            disabled={zoom >= 2}
            aria-label="放大字号"
          >
            <ZoomIn className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            className="btn-icon"
            onClick={handleCopy}
            disabled={!file.parsedMarkdown}
            aria-label="复制解析结果"
          >
            {copied ? (
              <Check className="size-3.5 text-green-600" />
            ) : (
              <Copy className="size-3.5" />
            )}
          </Button>
        </div>
      </div>

      <Separator />

      {/* 内容区 */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="p-3">
          {file.status !== "done" && (
            <div className="text-center text-xs text-muted-foreground py-8">
              {file.status === "uploading" && "文件上传中…"}
              {file.status === "parsing" && "正在解析文档…"}
              {file.status === "failed" && (
                <span className="text-destructive">
                  解析失败：{file.errorMessage ?? "未知错误"}
                </span>
              )}
            </div>
          )}
          {file.status === "done" && file.parsedMarkdown && (
            <MarkdownRenderer
              content={file.parsedMarkdown}
              className={zoomClass}
            />
          )}
          {file.status === "done" && !file.parsedMarkdown && (
            <div className="text-center text-xs text-muted-foreground py-8">
              文档已解析，但未返回可显示内容
            </div>
          )}
        </div>
      </ScrollArea>

      {/* 底部信息条 */}
      <div className="border-t border-border px-3 py-2 flex items-center justify-between text-[11px] text-muted-foreground">
        <span>解析时间：{formatDateTime(parsedAt)}</span>
        <a
          href="#"
          onClick={(e) => e.preventDefault()}
          className="inline-flex items-center gap-1 hover:text-foreground"
        >
          <ExternalLink className="size-3" />
          原文（mock）
        </a>
      </div>
    </div>
  );
}

function statusLabel(status: FileTagData["status"]): string {
  switch (status) {
    case "uploading":
      return "上传中";
    case "parsing":
      return "解析中";
    case "done":
      return "已解析";
    case "failed":
      return "失败";
  }
}
