"use client";

import { useMemo, useState } from "react";
import {
  BookOpen,
  ExternalLink,
  Filter,
  Quote,
  Search,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import type { Citation } from "@/types";

interface CitationListProps {
  /** 引用列表；未传入时读取当前消息的真实引用状态。 */
  citations?: Citation[];
  className?: string;
}

/**
 * §引用列表 右侧动态面板
 * 展示当前对话中所有引用的来源文献
 * 支持按来源筛选 + 关键词搜索 + 点击跳转原文
 */
export function CitationList({
  citations: propCitations,
  className,
}: CitationListProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const storeCitations = useAppStore((s) => s.currentCitations);
  const citations = propCitations ?? storeCitations;
  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);

  const sources = useMemo(() => {
    const set = new Set<string>();
    citations.forEach((c) => set.add(c.source));
    return Array.from(set);
  }, [citations]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return citations.filter((c) => {
      if (sourceFilter && c.source !== sourceFilter) return false;
      if (!q) return true;
      return (
        c.title.toLowerCase().includes(q) ||
        c.snippet.toLowerCase().includes(q) ||
        c.source.toLowerCase().includes(q)
      );
    });
  }, [citations, query, sourceFilter]);

  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* 顶部搜索 + 筛选 */}
      <div className="px-3 py-2 border-b border-border space-y-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
          <Input
            type="text"
            placeholder="搜索引用标题/摘要"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className={cn("h-7 pl-7 text-xs", seniorMode && "h-12 pl-9 text-base")}
            aria-label="搜索引用"
          />
        </div>
        {sources.length > 0 && (
          <div className="flex items-center gap-1 flex-wrap">
            <Filter className={cn("size-3 text-muted-foreground shrink-0", seniorMode && "size-5")} />
            <button
              type="button"
              onClick={() => setSourceFilter(null)}
              className={cn(
                "text-[11px] px-1.5 py-0.5 rounded transition-colors",
                seniorMode && "min-h-12 px-3 text-base",
                sourceFilter === null
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/70"
              )}
            >
              全部
            </button>
            {sources.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSourceFilter(s)}
                className={cn(
                  "text-[11px] px-1.5 py-0.5 rounded truncate max-w-[120px] transition-colors",
                  seniorMode && "min-h-12 max-w-[180px] px-3 text-base",
                  sourceFilter === s
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-muted/70"
                )}
                title={s}
              >
                {s}
              </button>
            ))}
          </div>
        )}
        <div className={cn("flex items-center justify-between text-xs text-muted-foreground", seniorMode && "text-base")}>
          <span>共 {citations.length} 条引用</span>
          <span>显示 {filtered.length} 条</span>
        </div>
      </div>

      {/* 列表 */}
      <ScrollArea className="flex-1 min-h-0">
        <ol className="p-3 space-y-2">
          {filtered.length === 0 && (
            <li className={cn("text-center text-xs text-muted-foreground py-8", seniorMode && "text-base leading-relaxed")}>
              未找到匹配的引用
            </li>
          )}
          {filtered.map((c) => (
            <li key={c.id}>
              <CitationItem citation={c} seniorMode={seniorMode} />
            </li>
          ))}
        </ol>
      </ScrollArea>

      <Separator />
      <div className={cn("px-3 py-2 text-[11px] text-muted-foreground", seniorMode && "text-base leading-relaxed")}>
        引用来自本次对话实际使用的知识库、网页或上传文档；请结合题名、摘录和可用的公开链接核对原文。
      </div>
    </div>
  );
}

interface CitationItemProps {
  citation: Citation;
  seniorMode: boolean;
}

function isExternalCitationUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

function CitationItem({ citation, seniorMode }: CitationItemProps) {
  const externalUrl = isExternalCitationUrl(citation.url);
  return (
    <article className="rounded-lg border border-border bg-card p-2.5">
      <header className="flex items-start gap-2">
        <span className={cn("inline-flex items-center justify-center size-5 shrink-0 rounded-full bg-primary/10 text-primary text-[10px] font-bold mt-0.5", seniorMode && "size-8 text-base")}>
          {citation.id}
        </span>
        <div className="flex-1 min-w-0">
          <h4
            className={cn(
              "font-medium leading-snug",
              seniorMode ? "text-base" : "text-sm"
            )}
          >
            {citation.title}
          </h4>
          <div className={cn("flex items-center gap-1.5 mt-1 text-xs text-muted-foreground flex-wrap", seniorMode && "text-base")}>
            <Badge
              variant="outline"
              className={cn("text-[10px] py-0 gap-0.5", seniorMode && "h-auto min-h-8 px-3 text-base")}
            >
              <BookOpen className="size-2.5" />
              {citation.source}
            </Badge>
            {citation.publishedDate && (
              <span>{citation.publishedDate}</span>
            )}
          </div>
        </div>
      </header>
      <div className={cn("mt-2 flex items-start gap-1.5 text-xs text-muted-foreground leading-relaxed pl-7", seniorMode && "pl-10 text-base leading-8")}>
        <Quote className="size-3 shrink-0 mt-0.5 opacity-50" />
        <p className="line-clamp-3">{citation.snippet}</p>
      </div>
      <div className={cn("mt-2 pl-7", seniorMode && "pl-10")}>
        {externalUrl ? (
          <a
            href={citation.url}
            target="_blank"
            rel="noopener noreferrer"
            className={cn("inline-flex items-center gap-1 text-xs text-primary hover:underline", seniorMode && "min-h-12 text-base")}
          >
            <ExternalLink className="size-3" />
            查看原文
          </a>
        ) : (
          <p className={cn("text-xs text-muted-foreground", seniorMode && "text-base leading-relaxed")}>
            此来源没有公开原文链接；请核对题名与摘录。
          </p>
        )}
      </div>
    </article>
  );
}
