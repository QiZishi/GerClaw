import type { ThinkingBlock, ToolCallBlock } from "@/types";

export interface PublicAnalysisProjection {
  label: string;
  detail: string | null;
  expandable: boolean;
}

export interface PublicToolProjection {
  label: string;
  statusLabel: string;
  expandable: false;
}

const PUBLIC_TOOL_NAMES: Readonly<Record<string, string>> = {
  search_memory: "健康记录",
  search_knowledge: "医学检索",
  web_search: "联网搜索",
  local_knowledge_search: "本地知识库检索",
  Skill: "专业能力",
  skill: "专业能力",
};

export function projectPublicAnalysis(data: ThinkingBlock): PublicAnalysisProjection {
  if (data.status !== "thinking") {
    return {
      label: "分析已完成",
      detail: null,
      expandable: false,
    };
  }

  const detail = data.content.trim();
  return {
    label: "正在分析",
    detail: detail || null,
    expandable: detail.length > 0,
  };
}

export function projectPublicTool(data: ToolCallBlock): PublicToolProjection {
  const label = PUBLIC_TOOL_NAMES[data.toolName] ?? "辅助处理";
  const statusLabel =
    data.status === "running"
      ? "进行中"
      : data.status === "failed"
        ? "暂时不可用"
        : "完成";

  return {
    label,
    statusLabel,
    expandable: false,
  };
}
