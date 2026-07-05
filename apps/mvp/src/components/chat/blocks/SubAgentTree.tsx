"use client";

import { useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Loader2,
  Network,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { SubAgentNode } from "@/types";

interface SubAgentTreeProps {
  data: SubAgentNode;
}

/**
 * §4.2.3 子智能体调用树
 * 折叠树形结构，主智能体 → 子智能体调用链
 * 缩进 + border-l 表示层级
 */
export function SubAgentTree({ data }: SubAgentTreeProps) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="rounded-lg border border-border bg-muted/30 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-muted/50 transition-colors"
        aria-expanded={expanded}
      >
        <span className="flex items-center gap-2 text-sm">
          <Network className="size-4 text-muted-foreground" />
          <span className="font-medium">智能体调用链</span>
        </span>
        <ChevronDown
          className={cn(
            "size-4 text-muted-foreground transition-transform",
            expanded && "rotate-180"
          )}
        />
      </button>
      {expanded && (
        <div className="border-t border-border/60 px-3 py-2">
          <SubAgentNodeRow node={data} depth={0} />
        </div>
      )}
    </div>
  );
}

function SubAgentNodeRow({
  node,
  depth,
}: {
  node: SubAgentNode;
  depth: number;
}) {
  const hasChildren = !!node.children && node.children.length > 0;
  const [childExpanded, setChildExpanded] = useState(true);

  return (
    <div
      className={cn(
        "relative",
        depth > 0 && "ml-4 pl-3 border-l border-border"
      )}
    >
      <div className="flex items-center gap-2 py-1">
        {hasChildren ? (
          <button
            type="button"
            onClick={() => setChildExpanded((v) => !v)}
            className="text-muted-foreground hover:text-foreground shrink-0"
            aria-label={childExpanded ? "折叠" : "展开"}
          >
            {childExpanded ? (
              <ChevronDown className="size-3" />
            ) : (
              <ChevronRight className="size-3" />
            )}
          </button>
        ) : (
          <span className="w-3 shrink-0" aria-hidden />
        )}
        <Network className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="text-sm font-medium">{node.name}</span>
        <StatusBadge status={node.status} />
        {node.detail && (
          <span className="text-xs text-muted-foreground truncate">
            · {node.detail}
          </span>
        )}
      </div>
      {hasChildren && childExpanded && (
        <div className="mt-1">
          {node.children!.map((child) => (
            <SubAgentNodeRow key={child.id} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: SubAgentNode["status"] }) {
  switch (status) {
    case "running":
      return (
        <Badge variant="secondary" className="gap-1 text-blue-600">
          <Loader2 className="size-3 animate-spin" />
          运行中
        </Badge>
      );
    case "done":
      return (
        <Badge variant="secondary" className="gap-1 text-green-600">
          <Check className="size-3" />
          完成
        </Badge>
      );
    case "failed":
      return (
        <Badge variant="destructive" className="gap-1">
          <X className="size-3" />
          失败
        </Badge>
      );
  }
}
