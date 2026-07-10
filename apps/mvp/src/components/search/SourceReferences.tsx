"use client";

import { useState } from "react";
import Image from "next/image";
import { BookOpen, ChevronDown, ExternalLink, Globe, List } from "lucide-react";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import type { Citation } from "@/types";

interface SourceReferencesProps {
  citations: Citation[];
  className?: string;
}

function getFaviconUrl(url: string): string {
  try {
    const u = new URL(url);
    return `https://www.google.com/s2/favicons?domain=${u.hostname}&sz=32`;
  } catch {
    return "";
  }
}

export function SourceReferences({ citations, className }: SourceReferencesProps) {
  const [expanded, setExpanded] = useState(false);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const setRightPanel = useAppStore((s) => s.setRightPanel);
  const setCurrentCitations = useAppStore((s) => s.setCurrentCitations);

  if (!citations || citations.length === 0) return null;

  const handleViewAll = () => {
    setCurrentCitations(citations);
    setRightPanel("citations");
  };

  return (
    <div
      className={cn(
        "mt-2 rounded-lg border border-border/50 bg-muted/20",
        seniorMode ? "text-base" : "text-xs",
        className
      )}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={() => setExpanded((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded((v) => !v);
          }
        }}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 hover:bg-muted/40 transition-colors cursor-pointer"
        aria-expanded={expanded}
      >
        <span className="flex items-center gap-1.5 text-muted-foreground font-medium">
          <BookOpen className={cn("shrink-0", seniorMode ? "size-4" : "size-3.5")} />
          参考来源（{citations.length}）
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              handleViewAll();
            }}
            className={cn(
              "inline-flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors px-1.5 py-0.5 rounded hover:bg-muted/60",
              seniorMode ? "text-sm" : "text-[11px]"
            )}
            aria-label="在右侧面板查看全部引用"
          >
            <List className={seniorMode ? "size-3.5" : "size-3"} />
            查看全部
          </button>
          <ChevronDown
            className={cn(
              "shrink-0 text-muted-foreground/60 transition-transform",
              expanded && "rotate-180",
              seniorMode ? "size-4" : "size-3.5"
            )}
          />
        </div>
      </div>

      {expanded && (
        <div className="border-t border-border/40 px-2 py-2">
          <ul className="space-y-1.5">
            {citations.map((c) => {
              const faviconUrl = getFaviconUrl(c.url);
              return (
                <li key={c.id}>
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={cn(
                      "flex items-start gap-2 rounded-md px-2 py-1.5 hover:bg-muted/60 transition-colors group",
                      seniorMode ? "py-2" : "py-1.5"
                    )}
                  >
                    <span
                      className={cn(
                        "inline-flex items-center justify-center shrink-0 rounded-full bg-primary/10 text-primary font-semibold mt-0.5",
                        seniorMode ? "size-6 text-xs" : "size-4 text-[10px]"
                      )}
                    >
                      {c.id}
                    </span>
                    {faviconUrl ? (
                      <Image
                        src={faviconUrl}
                        alt=""
                        width={seniorMode ? 20 : 16}
                        height={seniorMode ? 20 : 16}
                        className={cn("shrink-0 rounded mt-0.5", seniorMode ? "size-5" : "size-4")}
                        unoptimized
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.display = "none";
                          const next = (e.target as HTMLImageElement).nextElementSibling as HTMLElement | null;
                          if (next) next.classList.remove("hidden");
                        }}
                      />
                    ) : null}
                    <Globe
                      className={cn(
                        "shrink-0 text-muted-foreground/50 mt-0.5 hidden",
                        seniorMode ? "size-5" : "size-4",
                        !faviconUrl && "block"
                      )}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start gap-1">
                        <span
                          className={cn(
                            "font-medium leading-snug text-foreground group-hover:text-primary transition-colors line-clamp-1",
                            seniorMode ? "text-sm" : "text-xs"
                          )}
                        >
                          {c.title}
                        </span>
                        <ExternalLink
                          className={cn(
                            "shrink-0 text-muted-foreground/40 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity",
                            seniorMode ? "size-3.5" : "size-3"
                          )}
                        />
                      </div>
                      <div
                        className={cn(
                          "text-muted-foreground/70 mt-0.5 flex items-center gap-1 flex-wrap",
                          seniorMode ? "text-xs" : "text-[11px]"
                        )}
                      >
                        <span className="truncate">{c.source}</span>
                        {c.publishedDate && (
                          <>
                            <span>·</span>
                            <span>{c.publishedDate}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </a>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
