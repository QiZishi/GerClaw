"use client";

import { useState, useCallback } from "react";
import { Check, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { exportConversationToMarkdown } from "@/lib/export";
import { toast } from "@/components/ui/toast";
import type { Message, MessageBlock } from "@/types";
import html2canvas from "html2canvas";
import jsPDF from "jspdf";
import { Document, Packer, Paragraph, TextRun } from "docx";
import { saveAs } from "file-saver";

type ExportFormat = "md" | "pdf" | "png" | "jpg" | "docx";

const FORMATS: { id: ExportFormat; label: string; ext: string }[] = [
  { id: "md", label: "MD", ext: "Markdown" },
  { id: "pdf", label: "PDF", ext: "PDF" },
  { id: "png", label: "PNG", ext: "PNG 图片" },
  { id: "jpg", label: "JPG", ext: "JPG 图片" },
  { id: "docx", label: "DOCX", ext: "Word 文档" },
];

interface ExportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  messages: Message[];
  defaultSelectedIds?: string[];
  title: string;
}

function extractPlainText(blocks: MessageBlock[]): string {
  return blocks
    .filter((b): b is Extract<MessageBlock, { kind: "text" }> => b.kind === "text")
    .map((b) => b.content)
    .join("\n");
}

function sanitizeFilename(name: string): string {
  return name.replace(/[\\/:*?"<>|]/g, "_").slice(0, 80) || "对话记录";
}

function waitForImages(container: HTMLElement): Promise<void> {
  const images = container.querySelectorAll("img");
  const promises = Array.from(images).map((img) => {
    if (img.complete) return Promise.resolve();
    return new Promise<void>((resolve) => {
      img.onload = () => resolve();
      img.onerror = () => resolve();
      setTimeout(resolve, 3000);
    });
  });
  return Promise.all(promises).then(() => {});
}

export function ExportDialog({
  open,
  onOpenChange,
  messages,
  defaultSelectedIds,
  title,
}: ExportDialogProps) {
  const [format, setFormat] = useState<ExportFormat>("md");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => {
    if (defaultSelectedIds && defaultSelectedIds.length > 0) {
      return new Set(defaultSelectedIds);
    }
    return new Set(messages.map((m) => m.id));
  });
  const [exporting, setExporting] = useState(false);

  const resetState = useCallback(() => {
    setFormat("md");
    setExporting(false);
  }, []);

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        setTimeout(resetState, 200);
      }
      onOpenChange(nextOpen);
    },
    [onOpenChange, resetState]
  );

  const toggleAll = useCallback(() => {
    if (selectedIds.size === messages.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(messages.map((m) => m.id)));
    }
  }, [selectedIds.size, messages]);

  const toggleMessage = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const selectedMessages = messages.filter((m) => selectedIds.has(m.id));

  const getPreviewText = (msg: Message): string => {
    const text = extractPlainText(msg.blocks).replace(/[#*`_~\[\]()>|-]/g, "").replace(/\s+/g, " ").trim();
    if (text.length > 50) return text.slice(0, 50) + "...";
    return text || "(图片/文件消息)";
  };

  const doExportMarkdown = useCallback(() => {
    const conv = selectedMessages.map((m) => ({
      role: m.role as "user" | "assistant",
      content: extractPlainText(m.blocks),
    }));
    exportConversationToMarkdown(title || "对话记录", conv);
  }, [selectedMessages, title]);

  const doExportDocx = useCallback(async () => {
    const dateStr = new Date().toLocaleString("zh-CN");
    const children: (typeof Paragraph.prototype)[] = [];

    children.push(
      new Paragraph({
        children: [new TextRun({ text: title || "对话记录", bold: true, size: 32 })],
      })
    );
    children.push(
      new Paragraph({
        children: [new TextRun({ text: `GerClaw 老年AI诊疗平台 — 对话记录`, size: 22 })],
      })
    );
    children.push(
      new Paragraph({
        children: [new TextRun({ text: `导出时间：${dateStr}`, size: 20, color: "666666" })],
      })
    );
    children.push(new Paragraph({ children: [new TextRun({ text: "" })] }));

    for (const msg of selectedMessages) {
      const label = msg.role === "user" ? "用户：" : "GerClaw：";
      const content = extractPlainText(msg.blocks);
      children.push(
        new Paragraph({
          children: [
            new TextRun({
              text: label,
              bold: msg.role === "user",
              size: 24,
            }),
          ],
        })
      );
      const paragraphs = content.split("\n");
      for (const para of paragraphs) {
        children.push(
          new Paragraph({
            children: [
              new TextRun({
                text: para || " ",
                size: 22,
              }),
            ],
          })
        );
      }
      children.push(new Paragraph({ children: [new TextRun({ text: "" })] }));
    }

    const doc = new Document({
      sections: [{ properties: {}, children }],
    });

    const blob = await Packer.toBlob(doc);
    saveAs(blob, `${sanitizeFilename(title || "对话记录")}.docx`);
  }, [selectedMessages, title]);

  const doExportScreenshot = useCallback(
    async (type: "pdf" | "png" | "jpg") => {
      document.body.classList.add("exporting-screenshot");

      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));

      const allBubbles = Array.from(document.querySelectorAll<HTMLElement>("[data-message-bubble]"));
      const idToBubble = new Map<string, HTMLElement>();
      for (let i = 0; i < allBubbles.length; i++) {
        if (messages[i]) {
          idToBubble.set(messages[i].id, allBubbles[i]);
        }
      }

      const selectedBubbleEls = selectedMessages
        .map((m) => idToBubble.get(m.id))
        .filter((el): el is HTMLElement => !!el);

      if (selectedBubbleEls.length === 0) {
        document.body.classList.remove("exporting-screenshot");
        throw new Error("未找到可导出的消息");
      }

      const wrapper = document.createElement("div");
      wrapper.style.position = "absolute";
      wrapper.style.left = "-9999px";
      wrapper.style.top = "0";
      wrapper.style.width = "720px";
      wrapper.style.background = getComputedStyle(document.body).backgroundColor || "#ffffff";
      wrapper.style.padding = "24px";
      wrapper.style.fontFamily = getComputedStyle(document.body).fontFamily;
      wrapper.style.color = getComputedStyle(document.body).color || "#0f172a";

      const header = document.createElement("div");
      header.style.marginBottom = "24px";
      header.style.paddingBottom = "16px";
      header.style.borderBottom = "1px solid #e2e8f0";
      header.innerHTML = `<div style="font-size:20px;font-weight:700;margin-bottom:4px;">${title || "对话记录"}</div><div style="font-size:12px;color:#64748b;">GerClaw 老年AI诊疗平台 · ${new Date().toLocaleString("zh-CN")}</div>`;
      wrapper.appendChild(header);

      for (const bubble of selectedBubbleEls) {
        const clone = bubble.cloneNode(true) as HTMLElement;
        wrapper.appendChild(clone);
      }

      document.body.appendChild(wrapper);

      await waitForImages(wrapper);

      const canvas = await html2canvas(wrapper, {
        backgroundColor: "#ffffff",
        scale: 2,
        useCORS: true,
        logging: false,
      });

      document.body.removeChild(wrapper);
      document.body.classList.remove("exporting-screenshot");

      const filename = sanitizeFilename(title || "对话记录");

      if (type === "png") {
        canvas.toBlob(
          (blob) => {
            if (blob) saveAs(blob, `${filename}.png`);
          },
          "image/png"
        );
      } else if (type === "jpg") {
        canvas.toBlob(
          (blob) => {
            if (blob) saveAs(blob, `${filename}.jpg`);
          },
          "image/jpeg",
          0.92
        );
      } else {
        const imgData = canvas.toDataURL("image/png");
        const pdf = new jsPDF({
          orientation: "portrait",
          unit: "px",
          format: [canvas.width, canvas.height],
          hotfixes: ["px_scaling"],
        });

        const pdfWidth = pdf.internal.pageSize.getWidth();
        const pdfHeight = pdf.internal.pageSize.getHeight();
        const imgWidth = pdfWidth;
        const imgHeight = (canvas.height * imgWidth) / canvas.width;

        let heightLeft = imgHeight;
        let position = 0;

        pdf.addImage(imgData, "PNG", 0, position, imgWidth, imgHeight);
        heightLeft -= pdfHeight;

        while (heightLeft > 0) {
          position = heightLeft - imgHeight;
          pdf.addPage();
          pdf.addImage(imgData, "PNG", 0, position, imgWidth, imgHeight);
          heightLeft -= pdfHeight;
        }

        pdf.save(`${filename}.pdf`);
      }
    },
    [selectedMessages, messages, title]
  );

  const handleExport = useCallback(async () => {
    if (selectedMessages.length === 0) {
      toast.show("请至少选择一条消息");
      return;
    }

    setExporting(true);
    try {
      switch (format) {
        case "md":
          doExportMarkdown();
          toast.show("对话记录已导出为 Markdown");
          break;
        case "docx":
          await doExportDocx();
          toast.show("对话记录已导出为 Word 文档");
          break;
        case "pdf":
        case "png":
        case "jpg":
          await doExportScreenshot(format);
          toast.show(
            format === "pdf"
              ? "对话记录已导出为 PDF"
              : `对话记录已导出为 ${format.toUpperCase()} 图片`
          );
          break;
      }
      handleOpenChange(false);
    } catch (e) {
      console.error("Export failed:", e);
      toast.show("导出失败，请重试");
    } finally {
      setExporting(false);
    }
  }, [format, selectedMessages, doExportMarkdown, doExportDocx, doExportScreenshot, handleOpenChange]);

  const formatLabel = FORMATS.find((f) => f.id === format);
  const exportButtonText = exporting
    ? "导出中..."
    : `导出${formatLabel ? formatLabel.ext : ""}`;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-md p-0 gap-0 overflow-hidden">
        <DialogHeader className="px-5 pt-5 pb-3">
          <DialogTitle>导出对话</DialogTitle>
        </DialogHeader>

        <div className="px-5 pb-3">
          <div className="text-xs text-muted-foreground mb-2">选择格式</div>
          <div className="flex gap-2">
            {FORMATS.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setFormat(f.id)}
                className={cn(
                  "flex-1 py-2 px-2 rounded-lg border text-sm font-medium transition-all",
                  format === f.id
                    ? "border-primary bg-primary/10 text-primary ring-1 ring-primary"
                    : "border-border bg-background hover:border-primary/40 hover:bg-muted/40"
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        <div className="px-5 pb-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground">
              选择消息（{selectedIds.size}/{messages.length}）
            </span>
            <button
              type="button"
              onClick={toggleAll}
              className="text-xs text-primary hover:underline"
            >
              {selectedIds.size === messages.length ? "取消全选" : "全选"}
            </button>
          </div>
          <ScrollArea className="h-56 rounded-lg border border-border bg-muted/30">
            <div className="p-2 space-y-1">
              {messages.map((msg) => {
                const isUser = msg.role === "user";
                const isSelected = selectedIds.has(msg.id);
                return (
                  <label
                    key={msg.id}
                    className={cn(
                      "flex items-start gap-2 p-2 rounded-md cursor-pointer transition-colors",
                      isSelected ? "bg-primary/5" : "hover:bg-muted/50"
                    )}
                  >
                    <div
                      className={cn(
                        "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded border transition-colors",
                        isSelected
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-muted-foreground/40"
                      )}
                    >
                      {isSelected && <Check className="size-3" />}
                    </div>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleMessage(msg.id)}
                      className="sr-only"
                    />
                    <div className="min-w-0 flex-1">
                      <div
                        className={cn(
                          "text-xs font-medium mb-0.5",
                          isUser ? "text-primary" : "text-foreground"
                        )}
                      >
                        {isUser ? "用户" : "AI"}
                      </div>
                      <div className="text-xs text-muted-foreground truncate">
                        {getPreviewText(msg)}
                      </div>
                    </div>
                  </label>
                );
              })}
            </div>
          </ScrollArea>
        </div>

        <DialogFooter className="gap-2 px-5 py-4">
          <DialogClose
            render={<Button variant="outline" disabled={exporting}>取消</Button>}
          />
          <Button onClick={handleExport} disabled={exporting || selectedIds.size === 0}>
            {exporting && <Loader2 className="size-3.5 animate-spin mr-1.5" />}
            {exportButtonText}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
