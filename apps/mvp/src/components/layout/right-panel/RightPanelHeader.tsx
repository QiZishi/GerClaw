"use client";

import { Copy, X } from "lucide-react";

import { ExportButton } from "@/components/prescription/ExportButton";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import type { RightPanelType } from "@/types";

const EXPORTABLE: RightPanelType[] = ["prescription", "cga", "drug-review"];

export function RightPanelHeader({
  title,
  type,
  content,
  senior,
  onClose,
}: {
  title: string;
  type: NonNullable<RightPanelType>;
  content: string;
  senior: boolean;
  onClose: () => void;
}) {
  const copyContent = async () => {
    try {
      await navigator.clipboard.writeText(content);
      toast.show("已复制");
    } catch {
      toast.show("复制失败");
    }
  };

  return (
    <header className={cn("flex h-12 shrink-0 items-center justify-between gap-2 border-b border-border px-4", senior && "h-16")}>
      <span className={cn("font-medium text-sm", senior && "text-lg")}>{title}</span>
      <div className="flex items-center gap-1">
        {type !== "doc-editor" && content && (
          <Button
            variant="ghost"
            size={senior ? "default" : "icon-sm"}
            className={cn("btn-icon", senior && "min-h-12 gap-2 px-3 text-base")}
            onClick={() => void copyContent()}
            aria-label="复制内容"
            title="复制 Markdown 源码"
          >
            <Copy className="size-4" />
            {senior && <span>复制</span>}
          </Button>
        )}
        {EXPORTABLE.includes(type) && content && (
          <ExportButton title={title} content={content} variant="dropdown" />
        )}
        <Button
          variant="ghost"
          size={senior ? "default" : "icon-sm"}
          className={cn("btn-icon", senior && "min-h-12 gap-2 px-3 text-base")}
          onClick={onClose}
          aria-label="关闭"
        >
          <X className="size-4" />
          {senior && <span>关闭</span>}
        </Button>
      </div>
    </header>
  );
}
