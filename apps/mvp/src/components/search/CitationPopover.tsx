"use client";

import { ExternalLink, List } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import type { Citation } from "@/types";

interface CitationPopoverProps {
  citation: Citation;
  /** 角标编号 */
  index: number;
  /** 当前消息的所有引用（用于打开右侧面板） */
  allCitations?: Citation[];
}

function isExternalCitationUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

/**
 * 引用角标弹出卡片
 * 点击 [1] 弹出引用详情（标题、摘要、链接）
 * 提供"在右侧面板查看全部"选项
 * 样式：蓝色、小字号、上标、可点击
 */
export function CitationPopover({ citation, index, allCitations }: CitationPopoverProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const setRightPanel = useAppStore((s) => s.setRightPanel);
  const setCurrentCitations = useAppStore((s) => s.setCurrentCitations);
  const externalUrl = isExternalCitationUrl(citation.url);

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
            className={cn(
              "inline-flex items-center justify-center align-super font-bold cursor-pointer transition-colors",
              "text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300",
              "hover:bg-blue-50 dark:hover:bg-blue-950/40 rounded",
              seniorMode
                ? "text-[0.75em] min-w-[1.5em] h-[1.5em] px-0.5 mx-0.5"
                : "text-[0.7em] min-w-[1.25em] h-[1.25em] px-0.5 mx-0.5"
            )}
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
          <div className="break-words font-medium text-sm leading-snug">
            {citation.title}
          </div>
          <div className="break-words text-xs text-muted-foreground leading-relaxed line-clamp-3">
            {citation.snippet}
          </div>
          {citation.publishedDate && (
            <div className="text-xs text-muted-foreground">
              发布时间：{citation.publishedDate}
            </div>
          )}
          <div className="flex items-center gap-2 pt-1">
            {externalUrl ? (
              <a
                href={citation.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
              >
                <ExternalLink className="size-3" />
                查看原文
              </a>
            ) : (
              <span className="text-xs text-muted-foreground">此来源无公开链接</span>
            )}
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
