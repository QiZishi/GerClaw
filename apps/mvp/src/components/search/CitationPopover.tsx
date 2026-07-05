"use client";

import { ExternalLink } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Citation } from "@/types";

interface CitationPopoverProps {
  citation: Citation;
  /** 角标编号 */
  index: number;
}

/**
 * 引用角标弹出卡片
 * 点击 [1] 弹出引用详情（标题、摘要、链接）
 * shadcn 未装 Popover，用 DropdownMenu 替代
 */
export function CitationPopover({ citation, index }: CitationPopoverProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button
            type="button"
            className="inline-flex items-center justify-center align-super mx-0.5 size-5 rounded-full bg-primary/10 text-primary text-[10px] font-bold hover:bg-primary hover:text-primary-foreground transition-colors"
            aria-label={`查看引用 ${index}`}
          />
        }
      >
        {index}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-80 p-3">
        <div className="space-y-2">
          <div className="text-xs text-muted-foreground">
            引用 #{index} · {citation.source}
          </div>
          <div className="font-medium text-sm leading-snug">
            {citation.title}
          </div>
          <div className="text-xs text-muted-foreground leading-relaxed">
            {citation.snippet}
          </div>
          {citation.publishedDate && (
            <div className="text-xs text-muted-foreground">
              发布时间：{citation.publishedDate}
            </div>
          )}
          <a
            href={citation.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            <ExternalLink className="size-3" />
            查看原文
          </a>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
