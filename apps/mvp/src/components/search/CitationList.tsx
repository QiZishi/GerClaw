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
  /** 引用列表（默认从 store 获取 currentCitations，fallback 到 mock） */
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
  const citations = propCitations ?? (storeCitations.length > 0 ? storeCitations : defaultMockCitations);
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
            className="h-7 pl-7 text-xs"
            aria-label="搜索引用"
          />
        </div>
        {sources.length > 0 && (
          <div className="flex items-center gap-1 flex-wrap">
            <Filter className="size-3 text-muted-foreground shrink-0" />
            <button
              type="button"
              onClick={() => setSourceFilter(null)}
              className={cn(
                "text-[11px] px-1.5 py-0.5 rounded transition-colors",
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
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>共 {citations.length} 条引用</span>
          <span>显示 {filtered.length} 条</span>
        </div>
      </div>

      {/* 列表 */}
      <ScrollArea className="flex-1 min-h-0">
        <ol className="p-3 space-y-2">
          {filtered.length === 0 && (
            <li className="text-center text-xs text-muted-foreground py-8">
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
      <div className="px-3 py-2 text-[11px] text-muted-foreground">
        所有引用均来自公开医学文献/指南，禁止编造文献来源
      </div>
    </div>
  );
}

interface CitationItemProps {
  citation: Citation;
  seniorMode: boolean;
}

function CitationItem({ citation, seniorMode }: CitationItemProps) {
  return (
    <article className="rounded-lg border border-border bg-card p-2.5">
      <header className="flex items-start gap-2">
        <span className="inline-flex items-center justify-center size-5 shrink-0 rounded-full bg-primary/10 text-primary text-[10px] font-bold mt-0.5">
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
          <div className="flex items-center gap-1.5 mt-1 text-xs text-muted-foreground flex-wrap">
            <Badge
              variant="outline"
              className="text-[10px] py-0 gap-0.5"
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
      <div className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground leading-relaxed pl-7">
        <Quote className="size-3 shrink-0 mt-0.5 opacity-50" />
        <p className="line-clamp-3">{citation.snippet}</p>
      </div>
      <div className="mt-2 pl-7">
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
    </article>
  );
}

/** 内置 mock 引用数据（真实存在的指南/共识名称） */
const defaultMockCitations: Citation[] = [
  {
    id: 1,
    title: "中国老年高血压管理指南 2023",
    snippet:
      "老年高血压患者血压控制目标建议为 140/90 mmHg 以下；优先选择长效 CCB 或 ARB，注意体位性低血压风险。",
    url: "https://example.com/guideline/elderly-htn-2023",
    source: "中华医学会老年医学分会",
    publishedDate: "2023-06",
  },
  {
    id: 2,
    title: "中国 2 型糖尿病防治指南 2020",
    snippet:
      "老年 2 型糖尿病患者 HbA1c 控制目标应个体化；二甲双胍为一线用药，老年患者需根据 eGFR 调整剂量。",
    url: "https://example.com/guideline/t2dm-2020",
    source: "中华医学会糖尿病学分会",
    publishedDate: "2020-02",
  },
  {
    id: 3,
    title: "Beers 标准（2019 更新）：老年人潜在不适当用药",
    snippet:
      "老年人应避免长期使用苯二氮䓬类、第一代抗组胺药；螺内酯 >25mg/d 在心衰患者中风险增加。",
    url: "https://example.com/guideline/beers-2019",
    source: "美国老年医学会（AGS）",
    publishedDate: "2019-01",
  },
  {
    id: 4,
    title: "老年综合评估（CGA）临床应用专家共识",
    snippet:
      "CGA 涵盖躯体、功能、心理、社会环境等多维度评估，建议 65 岁以上合并多种慢性病的老年人常规开展。",
    url: "https://example.com/consensus/cga",
    source: "中华老年医学杂志",
    publishedDate: "2023-11",
  },
  {
    id: 5,
    title: "老年抑郁筛查与干预专家共识",
    snippet:
      "PHQ-9 量表为老年抑郁首选筛查工具，得分 ≥10 提示中重度抑郁，需结合临床评估并启动干预。",
    url: "https://example.com/consensus/elderly-depression",
    source: "中华医学会精神病学分会",
    publishedDate: "2022-09",
  },
];
