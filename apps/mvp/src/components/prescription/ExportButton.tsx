"use client";

import { useState } from "react";
import { Download, FileText, FileType2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ExportFormat } from "@/types";

interface ExportButtonProps {
  className?: string;
  onExport?: (format: ExportFormat) => void;
}

/**
 * §结果导出 — 导出按钮组
 * PDF / Markdown / DOCX 三个图标按钮
 * mock 阶段：点击弹 Toast"导出功能将在 0002 阶段接入"
 */
export function ExportButton({ className, onExport }: ExportButtonProps) {
  const [toast, setToast] = useState<string | null>(null);

  const handle = (format: ExportFormat) => {
    if (onExport) {
      onExport(format);
      return;
    }
    setToast(`已请求导出 ${format.toUpperCase()}，导出功能将在 0002 阶段接入`);
    setTimeout(() => setToast(null), 2000);
  };

  const buttons: { format: ExportFormat; label: string; icon: typeof FileText }[] = [
    { format: "pdf", label: "PDF", icon: FileText },
    { format: "markdown", label: "MD", icon: FileType2 },
    { format: "docx", label: "DOCX", icon: Download },
  ];

  return (
    <div className={cn("relative", className)}>
      <div className="flex items-center gap-1.5">
        {buttons.map((b) => (
          <Button
            key={b.format}
            variant="outline"
            size="sm"
            className="gap-1"
            onClick={() => handle(b.format)}
            aria-label={`导出为 ${b.label}`}
          >
            <b.icon className="size-3.5" />
            <span>{b.label}</span>
          </Button>
        ))}
      </div>
      {toast && (
        <div
          role="status"
          aria-live="polite"
          className="absolute top-full right-0 mt-1 z-10 rounded-md border border-border bg-popover px-3 py-1.5 text-xs text-popover-foreground shadow-md whitespace-nowrap"
        >
          {toast}
        </div>
      )}
    </div>
  );
}
