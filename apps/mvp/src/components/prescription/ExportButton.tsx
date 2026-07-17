"use client";

import { useState } from "react";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import React from "react";
import {
  Download,
  FileText,
  FileImage,
  FileType,
  File,
  Check,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import {
  exportToMarkdown,
  exportToDocx,
  exportToPdf,
  exportToPng,
  exportToJpg,
} from "@/lib/export";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";
import { toast } from "@/components/ui/toast";

/** Export is a presentation concern; it must not depend on clinical-report types. */
type ExportFormat = "markdown" | "png" | "jpg" | "pdf" | "docx";

interface ExportButtonProps {
  className?: string;
  title: string;
  content: string;
  subtitle?: string;
  variant?: "buttons" | "dropdown";
}

const FORMAT_OPTIONS: {
  value: ExportFormat;
  label: string;
  icon: React.ReactNode;
}[] = [
  { value: "markdown", label: "Markdown (.md)", icon: <File className="size-4" /> },
  { value: "png", label: "PNG 图片", icon: <FileImage className="size-4" /> },
  { value: "jpg", label: "JPG 图片", icon: <FileImage className="size-4" /> },
  { value: "pdf", label: "PDF (.pdf)", icon: <FileText className="size-4" /> },
  { value: "docx", label: "Word (.docx)", icon: <FileType className="size-4" /> },
];

async function renderToTempElement(
  content: string,
  title: string,
  subtitle?: string
): Promise<{ element: HTMLElement; cleanup: () => void }> {
  const tempContainer = document.createElement("div");
  tempContainer.style.position = "absolute";
  tempContainer.style.left = "-9999px";
  tempContainer.style.top = "0";
  tempContainer.style.width = "794px";
  tempContainer.style.backgroundColor = "#ffffff";
  tempContainer.style.padding = "40px";
  tempContainer.style.fontFamily = "system-ui, -apple-system, sans-serif";

  const tempHeader = document.createElement("div");
  tempHeader.style.marginBottom = "24px";
  tempHeader.style.borderBottom = "1px solid #e5e7eb";
  tempHeader.style.paddingBottom = "16px";

  const tempTitle = document.createElement("h1");
  tempTitle.textContent = title;
  tempTitle.style.fontSize = "24px";
  tempTitle.style.fontWeight = "bold";
  tempTitle.style.color = "#111827";
  tempTitle.style.margin = "0 0 8px 0";
  tempHeader.appendChild(tempTitle);

  if (subtitle) {
    const tempSubtitle = document.createElement("p");
    tempSubtitle.textContent = subtitle;
    tempSubtitle.style.fontSize = "14px";
    tempSubtitle.style.color = "#6b7280";
    tempSubtitle.style.margin = "0";
    tempHeader.appendChild(tempSubtitle);
  }

  tempContainer.appendChild(tempHeader);

  const tempContent = document.createElement("div");
  tempContainer.appendChild(tempContent);
  document.body.appendChild(tempContainer);

  const root = createRoot(tempContent);
  flushSync(() => {
    root.render(
      React.createElement(MarkdownRenderer, {
        content,
        className: "text-sm leading-relaxed",
      })
    );
  });
  await document.fonts?.ready;
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

  const cleanup = () => {
    root.unmount();
    tempContainer.remove();
  };

  return { element: tempContainer, cleanup };
}

export function ExportButton({
  className,
  title,
  content,
  subtitle,
  variant = "buttons",
}: ExportButtonProps) {
  const [exported, setExported] = useState(false);
  const [exportingFormat, setExportingFormat] = useState<ExportFormat | null>(null);

  const handleExport = async (format: ExportFormat) => {
    setExportingFormat(format);
    let tempCleanup: (() => void) | null = null;

    try {
      switch (format) {
        case "markdown":
          exportToMarkdown({ title, content, subtitle });
          toast.show("Markdown 文件已下载");
          break;
        case "docx":
          await exportToDocx(title, content, subtitle);
          toast.show("Word 文档已下载");
          break;
        case "pdf": {
          let exportElement: HTMLElement | null = document.getElementById(
            "panel-export-content"
          );

          if (!exportElement) {
            const { element, cleanup } = await renderToTempElement(
              content,
              title,
              subtitle
            );
            exportElement = element;
            tempCleanup = cleanup;
          }

          await exportToPdf(exportElement, title);
          toast.show("PDF 文件已下载");
          break;
        }
        case "png": {
          const { element, cleanup } = await renderToTempElement(
            content,
            title,
            subtitle
          );
          tempCleanup = cleanup;
          await exportToPng(element, title);
          toast.show("PNG 图片已下载");
          break;
        }
        case "jpg": {
          const { element, cleanup } = await renderToTempElement(
            content,
            title,
            subtitle
          );
          tempCleanup = cleanup;
          await exportToJpg(element, title);
          toast.show("JPG 图片已下载");
          break;
        }
      }
      setExported(true);
      setTimeout(() => setExported(false), 2000);
    } catch (err) {
      console.error("Export failed:", err);
      const formatLabels: Record<ExportFormat, string> = {
        markdown: "Markdown",
        png: "PNG",
        jpg: "JPG",
        pdf: "PDF",
        docx: "Word",
      };
      toast.show(`${formatLabels[format]} 导出失败，请重试`);
    } finally {
      if (tempCleanup) {
        tempCleanup();
      }
      setExportingFormat(null);
    }
  };

  if (variant === "dropdown") {
    return (
      <div className={cn("relative", className)}>
        <DropdownMenu>
          <DropdownMenuTrigger>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              aria-label="导出"
              disabled={exportingFormat !== null}
            >
              {exported ? (
                <Check className="size-3.5 text-green-600" />
              ) : exportingFormat ? (
                <Loader2 className="size-3.5" aria-hidden />
              ) : (
                <Download className="size-3.5" />
              )}
              <span>
                {exported
                  ? "已导出"
                  : exportingFormat
                  ? "导出中..."
                  : "导出"}
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" sideOffset={4}>
            {FORMAT_OPTIONS.map((opt) => (
              <DropdownMenuItem
                key={opt.value}
                onClick={() => handleExport(opt.value)}
                disabled={exportingFormat !== null}
              >
                {opt.icon}
                {opt.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    );
  }

  return (
    <div className={cn("flex items-center gap-1.5", className)}>
      {FORMAT_OPTIONS.map((opt) => {
        const isExporting = exportingFormat === opt.value;
        return (
          <Button
            key={opt.value}
            variant="outline"
            size="sm"
            className="gap-1"
            onClick={() => handleExport(opt.value)}
            aria-label={`导出为 ${opt.label}`}
            disabled={exportingFormat !== null}
          >
            {exported && isExporting ? (
              <Check className="size-3.5 text-green-600" />
            ) : isExporting ? (
              <Loader2 className="size-3.5" aria-hidden />
            ) : (
              opt.icon
            )}
            <span className="text-xs">
              {opt.value === "markdown"
                ? "MD"
                : opt.value === "docx"
                ? "DOCX"
                : opt.value.toUpperCase()}
            </span>
          </Button>
        );
      })}
    </div>
  );
}
