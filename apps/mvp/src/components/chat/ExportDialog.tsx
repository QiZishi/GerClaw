"use client";

import { useState, useRef } from "react";
import {
  Download,
  FileText,
  FileImage,
  FileType,
  File,
  Check,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "@/components/ui/toast";
import type { Message } from "@/types";
import {
  buildConversationPlainText,
  exportConversationToDocx,
  exportConversationToMarkdown,
  exportToJpg,
  exportToPdf,
  exportToPng,
  MEDICAL_EXPORT_DISCLAIMER,
  downloadBlob,
  sanitizeFilename,
} from "@/lib/export";

type ExportFormat = "png" | "jpg" | "pdf" | "docx" | "md" | "txt";

interface ExportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  messages: Message[];
  defaultSelectedIds?: string[];
  title?: string;
}

const FORMAT_OPTIONS: { value: ExportFormat; label: string; icon: React.ReactNode }[] = [
  { value: "md", label: "Markdown", icon: <File className="size-4" /> },
  { value: "txt", label: "文本", icon: <File className="size-4" /> },
  { value: "png", label: "PNG", icon: <FileImage className="size-4" /> },
  { value: "jpg", label: "JPG", icon: <FileImage className="size-4" /> },
  { value: "pdf", label: "PDF", icon: <FileText className="size-4" /> },
  { value: "docx", label: "DOCX", icon: <FileType className="size-4" /> },
];

function getMessagePreview(msg: Message): string {
  const textBlock = msg.blocks.find((b) => b.kind === "text");
  if (textBlock && "content" in textBlock) {
    return textBlock.content.slice(0, 50) + (textBlock.content.length > 50 ? "..." : "");
  }
  const emergencyAlert = msg.blocks.find((b) => b.kind === "emergency_alert");
  if (emergencyAlert) {
    return emergencyAlert.data.message.slice(0, 50) + (emergencyAlert.data.message.length > 50 ? "..." : "");
  }
  return "[空消息]";
}

function getMessageText(msg: Message): string {
  const text = msg.blocks
    .filter((b) => b.kind === "text" && "content" in b)
    .map((b) => (b as { content: string }).content)
    .join("\n")
    .trim();
  if (text) return text;

  // 紧急分流的内容以专门的可访问警告块渲染，而非普通文本块。导出必须
  // 保留同一条服务端确认的就医提示，不能让用户得到“空消息”的记录。
  return msg.blocks
    .filter((block) => block.kind === "emergency_alert")
    .map((block) => block.data.message)
    .join("\n")
    .trim();
}

function exportableMessages(messages: Message[]) {
  return messages.map((message) => ({
    role: message.role === "user" ? "user" as const : "assistant" as const,
    content: getMessageText(message),
  }));
}

export function ExportDialog({
  open,
  onOpenChange,
  messages,
  defaultSelectedIds = [],
  title = "对话导出",
}: ExportDialogProps) {
  const [format, setFormat] = useState<ExportFormat>("md");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set(defaultSelectedIds));
  const [exporting, setExporting] = useState(false);
  const exportContainerRef = useRef<HTMLDivElement>(null);

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const selectAll = () => {
    setSelectedIds(new Set(messages.map((m) => m.id)));
  };

  const selectNone = () => {
    setSelectedIds(new Set());
  };

  const selectedMessages = messages.filter((m) => selectedIds.has(m.id));

  const handleExport = async () => {
    if (selectedMessages.length === 0) {
      toast.show("请至少选择一条消息");
      return;
    }
    setExporting(true);
    try {
      switch (format) {
        case "md":
          exportConversationToMarkdown(title, exportableMessages(selectedMessages));
          toast.show("已导出为 Markdown");
          break;
        case "txt":
          downloadBlob(
            new Blob([buildConversationPlainText(title, exportableMessages(selectedMessages))], { type: "text/plain;charset=utf-8" }),
            `${sanitizeFilename(title)}.txt`
          );
          toast.show("已导出为文本");
          break;
        case "png": {
          if (exportContainerRef.current) {
            exportContainerRef.current.style.display = "block";
            try {
              await exportToPng(exportContainerRef.current, title);
              toast.show("已导出为 PNG 图片");
            } finally {
              exportContainerRef.current.style.display = "none";
            }
          }
          break;
        }
        case "jpg": {
          if (exportContainerRef.current) {
            exportContainerRef.current.style.display = "block";
            try {
              await exportToJpg(exportContainerRef.current, title);
              toast.show("已导出为 JPG 图片");
            } finally {
              exportContainerRef.current.style.display = "none";
            }
          }
          break;
        }
        case "pdf": {
          if (exportContainerRef.current) {
            exportContainerRef.current.style.display = "block";
            try {
              await exportToPdf(exportContainerRef.current, title);
              toast.show("已导出为 PDF");
            } finally {
              exportContainerRef.current.style.display = "none";
            }
          }
          break;
        }
        case "docx": {
          await exportConversationToDocx(title, exportableMessages(selectedMessages));
          toast.show("已导出为 DOCX 文档");
          break;
        }
      }
      onOpenChange(false);
    } catch (err) {
      console.error("Export failed:", err);
      toast.show("导出失败，请重试");
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-lg max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Download className="size-5" />
              导出对话
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 flex-1 min-h-0 overflow-y-auto">
            <div>
              <div className="text-sm font-medium mb-2">导出格式</div>
              <div className="flex gap-2">
                {FORMAT_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setFormat(opt.value)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm border transition-colors ${
                      format === opt.value
                        ? "bg-primary text-primary-foreground border-primary"
                        : "bg-muted/30 border-border hover:bg-muted/50"
                    }`}
                  >
                    {opt.icon}
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-medium">选择消息</div>
                <div className="flex gap-2 text-xs">
                  <button
                    type="button"
                    onClick={selectAll}
                    className="text-primary hover:underline"
                  >
                    全选
                  </button>
                  <span className="text-muted-foreground">|</span>
                  <button
                    type="button"
                    onClick={selectNone}
                    className="text-muted-foreground hover:underline"
                  >
                    全不选
                  </button>
                </div>
              </div>
              <div className="border border-border rounded-lg divide-y divide-border max-h-64 overflow-y-auto">
                {messages.map((msg) => {
                  const isSelected = selectedIds.has(msg.id);
                  return (
                    <label
                      key={msg.id}
                      className="flex items-start gap-3 p-3 hover:bg-muted/30 cursor-pointer transition-colors"
                    >
                      <Checkbox
                        checked={isSelected}
                        onCheckedChange={() => toggleSelect(msg.id)}
                        className="mt-0.5"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span
                            className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                              msg.role === "user"
                                ? "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                                : "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300"
                            }`}
                          >
                            {msg.role === "user" ? "用户" : "AI"}
                          </span>
                          {isSelected && (
                            <Check className="size-3 text-primary" />
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground truncate">
                          {getMessagePreview(msg)}
                        </p>
                      </div>
                    </label>
                  );
                })}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                已选择 {selectedMessages.length} 条消息
              </div>
            </div>
          </div>

          <DialogFooter className="gap-2">
            <DialogClose render={<Button variant="outline" />}>
              取消
            </DialogClose>
            <Button onClick={handleExport} disabled={exporting || selectedMessages.length === 0}>
              {exporting ? "导出中..." : "导出"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 隐藏的导出容器，用于截图 */}
      <div
        ref={exportContainerRef}
        data-html2canvas-ignore={false}
        className="fixed -left-[9999px] top-0 w-[600px] bg-white p-8"
        style={{ display: "none" }}
      >
        <h1 className="text-xl font-bold text-gray-900 mb-6">{title}</h1>
        {selectedMessages.map((msg) => (
          <div key={msg.id} className="mb-4">
            <div className="text-xs text-gray-500 mb-1">
              {msg.role === "user" ? "用户" : "AI助手"} ·{" "}
              {new Date(msg.createdAt).toLocaleString("zh-CN")}
            </div>
            <div
              className={`p-3 rounded-lg text-sm leading-relaxed whitespace-pre-wrap ${
                msg.role === "user" ? "bg-blue-50 text-gray-900" : "bg-gray-50 text-gray-900"
              }`}
            >
              {getMessageText(msg)}
            </div>
          </div>
        ))}
        <p className="mt-6 border-t border-gray-200 pt-4 text-xs leading-relaxed text-gray-600">
          医疗免责声明：{MEDICAL_EXPORT_DISCLAIMER}
        </p>
      </div>
    </>
  );
}
