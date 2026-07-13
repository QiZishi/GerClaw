"use client";

import { useState, useRef, useEffect } from "react";
import { createRoot } from "react-dom/client";
import React from "react";
import { Download, FileText, FileType2, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { exportToMarkdown, exportToDocx, exportToPdf } from "@/lib/export";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";
import { toast } from "@/components/ui/toast";
import type { ExportFormat } from "@/types";

interface ExportButtonProps {
  className?: string;
  title: string;
  content: string;
  subtitle?: string;
  variant?: "buttons" | "dropdown";
}

export function ExportButton({ className, title, content, subtitle, variant = "buttons" }: ExportButtonProps) {
  const [exported, setExported] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen]);

  const handleMarkdown = () => {
    try {
      exportToMarkdown({ title, content, subtitle });
      setExported(true);
      toast.show("Markdown 文件已下载");
      setTimeout(() => setExported(false), 2000);
    } catch {
      toast.show("导出失败，请重试");
    }
    setMenuOpen(false);
  };

  const handleDocx = async () => {
    try {
      await exportToDocx(title, content, subtitle);
      setExported(true);
      toast.show("Word 文档已下载");
      setTimeout(() => setExported(false), 2000);
    } catch {
      toast.show("导出失败，请重试");
    }
    setMenuOpen(false);
  };

  const handlePdf = async () => {
    setMenuOpen(false);
    if (isExportingPdf) return;
    setIsExportingPdf(true);

    try {
      let exportElement: HTMLElement | null = document.getElementById("panel-export-content");

      if (!exportElement) {
        const tempContainer = document.createElement("div");
        tempContainer.style.position = "absolute";
        tempContainer.style.left = "-9999px";
        tempContainer.style.top = "0";
        tempContainer.style.width = "794px";
        tempContainer.style.backgroundColor = "#ffffff";
        tempContainer.style.padding = "40px";
        tempContainer.style.fontFamily = "system-ui, -apple-system, sans-serif";
        tempContainer.id = "temp-pdf-export";

        const tempContent = document.createElement("div");
        tempContainer.appendChild(tempContent);
        document.body.appendChild(tempContainer);

        const renderRoot = createRoot(tempContent);
        renderRoot.render(React.createElement(MarkdownRenderer, { content, className: "text-sm leading-relaxed" }));

        await new Promise(resolve => setTimeout(resolve, 800));
        
        exportElement = tempContainer;
        await exportToPdf(exportElement, title);
        
        setTimeout(() => {
          renderRoot.unmount();
          if (tempContainer.parentNode) {
            document.body.removeChild(tempContainer);
          }
        }, 100);
      } else {
        await exportToPdf(exportElement, title);
      }

      setExported(true);
      toast.show("PDF 文件已下载");
      setTimeout(() => setExported(false), 2000);
    } catch (err) {
      console.error("PDF export failed:", err);
      toast.show("PDF 导出失败，请重试");
    } finally {
      setIsExportingPdf(false);
    }
  };

  const handle = (format: ExportFormat) => {
    if (format === "markdown") {
      handleMarkdown();
      return;
    }
    if (format === "docx") {
      handleDocx();
      return;
    }
    handlePdf();
  };

  if (variant === "dropdown") {
    return (
      <div className={cn("relative", className)} ref={menuRef}>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={() => setMenuOpen(!menuOpen)}
          aria-label="导出"
          disabled={isExportingPdf}
        >
          {exported ? <Check className="size-3.5 text-green-600" /> : isExportingPdf ? <Download className="size-3.5 animate-pulse" /> : <Download className="size-3.5" />}
          <span>{exported ? "已导出" : isExportingPdf ? "导出中..." : "导出"}</span>
        </Button>
        {menuOpen && (
          <div className="absolute right-0 top-full mt-1 z-50 min-w-36 rounded-lg bg-popover p-1 text-popover-foreground shadow-md ring-1 ring-foreground/10">
            <button
              type="button"
              onClick={handleMarkdown}
              className="w-full flex items-center gap-2 px-2.5 py-1.5 text-sm rounded hover:bg-muted transition-colors"
            >
              <FileType2 className="size-3.5" />
              <span>Markdown (.md)</span>
            </button>
            <button
              type="button"
              onClick={handleDocx}
              className="w-full flex items-center gap-2 px-2.5 py-1.5 text-sm rounded hover:bg-muted transition-colors"
            >
              <Download className="size-3.5" />
              <span>Word (.docx)</span>
            </button>
            <button
              type="button"
              onClick={handlePdf}
              disabled={isExportingPdf}
              className="w-full flex items-center gap-2 px-2.5 py-1.5 text-sm rounded hover:bg-muted transition-colors disabled:opacity-50"
            >
              <FileText className="size-3.5" />
              <span>{isExportingPdf ? "导出中..." : "PDF (.pdf)"}</span>
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={cn("flex items-center gap-1.5", className)}>
      <Button
        variant="outline"
        size="sm"
        className="gap-1"
        onClick={() => handle("markdown")}
        aria-label="导出为 Markdown"
      >
        {exported ? <Check className="size-3.5 text-green-600" /> : <FileType2 className="size-3.5" />}
        <span>MD</span>
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="gap-1"
        onClick={() => handle("pdf")}
        aria-label="导出为 PDF"
        disabled={isExportingPdf}
      >
        <FileText className="size-3.5" />
        <span>PDF</span>
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="gap-1"
        onClick={() => handle("docx")}
        aria-label="导出为 DOCX"
      >
        <Download className="size-3.5" />
        <span>DOCX</span>
      </Button>
    </div>
  );
}
