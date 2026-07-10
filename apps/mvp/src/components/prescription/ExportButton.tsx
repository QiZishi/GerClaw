"use client";

import { useState } from "react";
import { Download, FileText, FileType2, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { exportToMarkdown } from "@/lib/export";
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

  const handleMarkdown = () => {
    try {
      exportToMarkdown({ title, content, subtitle });
      setExported(true);
      toast.show("Markdown 文件已下载");
      setTimeout(() => setExported(false), 2000);
    } catch {
      toast.show("导出失败，请重试");
    }
  };

  const handle = (format: ExportFormat) => {
    if (format === "markdown") {
      handleMarkdown();
      return;
    }
    toast.show(`${format.toUpperCase()} 导出即将推出，当前支持 Markdown 导出`);
  };

  if (variant === "dropdown") {
    return (
      <div className={cn("relative", className)}>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={handleMarkdown}
          aria-label="导出"
        >
          {exported ? <Check className="size-3.5 text-green-600" /> : <Download className="size-3.5" />}
          <span>{exported ? "已导出" : "导出"}</span>
        </Button>
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
        className="gap-1 opacity-50"
        onClick={() => handle("pdf")}
        aria-label="导出为 PDF（即将推出）"
      >
        <FileText className="size-3.5" />
        <span>PDF</span>
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="gap-1 opacity-50"
        onClick={() => handle("docx")}
        aria-label="导出为 DOCX（即将推出）"
      >
        <Download className="size-3.5" />
        <span>DOCX</span>
      </Button>
    </div>
  );
}
