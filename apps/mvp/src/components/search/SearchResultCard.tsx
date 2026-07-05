"use client";

import { ExternalLink, Globe } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAppStore } from "@/stores/appStore";
import type { SearchResultItem } from "@/types";

interface SearchResultCardProps {
  item: SearchResultItem;
  /** 引用编号（如 1/2/3），用于在 AI 文本中作为角标 */
  index?: number;
}

/**
 * §4.2.3 联网搜索结果卡片
 * 标题 + 来源 favicon + 摘要 + 链接
 * 点击链接可在右侧面板预览
 */
export function SearchResultCard({ item, index }: SearchResultCardProps) {
  const setRightPanel = useAppStore((s) => s.setRightPanel);

  const handleOpenPreview = () => {
    setRightPanel("file-preview");
  };

  return (
    <Card className="bg-muted/40 border-border/60">
      <CardHeader className="pb-2">
        <div className="flex items-start gap-2">
          <Globe className="size-4 shrink-0 text-muted-foreground mt-0.5" />
          <div className="flex-1 min-w-0">
            <CardTitle className="text-sm leading-snug">
              {index !== undefined && (
                <span className="inline-flex items-center justify-center size-4 mr-1 rounded-full bg-primary text-primary-foreground text-[10px] font-bold align-middle">
                  {index}
                </span>
              )}
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-primary hover:underline"
                onClick={(e) => {
                  // 桌面端：默认新标签页打开；同时触发预览
                  e.preventDefault();
                  handleOpenPreview();
                }}
              >
                {item.title}
              </a>
            </CardTitle>
            <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
              <span className="truncate">{item.source}</span>
              {item.publishedDate && (
                <>
                  <span>·</span>
                  <span>{item.publishedDate}</span>
                </>
              )}
            </div>
          </div>
          <ExternalLink className="size-3.5 shrink-0 text-muted-foreground" />
        </div>
      </CardHeader>
      <CardContent className="text-xs text-muted-foreground leading-relaxed">
        {item.snippet}
      </CardContent>
    </Card>
  );
}
