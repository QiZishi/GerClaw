"use client";

import { ExternalLink, List } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAppStore } from "@/stores/appStore";
import type { Citation } from "@/types";

interface CitationPopoverProps {
  citation: Citation;
  /** 角标编号 */
  index: number;
  /** 当前消息的所有引用（用于打开右侧面板） */
  allCitations?: Citation[];
}

/**
 * 引用角标弹出卡片
 * 点击 [1] 弹出引用详情（标题、摘要、链接）
 * 提供"在右侧面板查看全部"选项
 */
export function CitationPopover({ citation, index, allCitations }: CitationPopoverProps) {
  const setRightPanel = useAppStore((s) => s.setRightPanel);
  const setCurrentCitations = useAppStore((s) => s.setCurrentCitations);

  const handleOpenAllCitations = () => {
    if (allCitations && allCitations.length > 0) {
      setCurrentCitations(allCitations);
    } else {
      setCurrentCitations([citation]);
    }
    setRightPanel("citations");
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button
            type="button"
            className="inline-flex items-center justify-center align-super mx-0.5 size-5 min-w-5 px-1 rounded-full bg-primary/10 text-primary text-[10px] font-bold hover:bg-primary hover:text-primary-foreground transition-colors cursor-pointer"
            aria-label={`查看引用 ${index}`}
          >
            {index}
          </button>
        }
      />
      <DropdownMenuContent align="start" className="w-80 p-3">
        <div className="space-y-2">
          <div className="text-xs text-muted-foreground">
            引用 #{index} · {citation.source}
          </div>
          <div className="font-medium text-sm leading-snug">
            {citation.title}
          </div>
          <div className="text-xs text-muted-foreground leading-relaxed line-clamp-3">
            {citation.snippet}
          </div>
          {citation.publishedDate && (
            <div className="text-xs text-muted-foreground">
              发布时间：{citation.publishedDate}
            </div>
          )}
          <div className="flex items-center gap-2 pt-1">
            <a
              href={citation.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
            >
              <ExternalLink className="size-3" />
              查看原文
            </a>
            <button
              type="button"
              onClick={handleOpenAllCitations}
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <List className="size-3" />
              查看全部引用
            </button>
          </div>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
