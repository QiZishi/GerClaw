"use client";

import { useState } from "react";

import { ArtifactWorkspace } from "@/components/artifact/ArtifactWorkspace";
import { MarkdownEditor } from "@/components/editor/MarkdownEditor";
import { HelpPanel } from "@/components/help/HelpPanel";
import { HealthProfilePanel } from "@/components/health/HealthProfilePanel";
import { FileUpload } from "@/components/document/FileUpload";
import { DocumentPreview } from "@/components/document/DocumentPreview";
import { CitationList } from "@/components/search/CitationList";
import { SettingsPanel } from "@/components/settings/SettingsPanel";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/appStore";
import type { FileTag, RightPanelType, Role } from "@/types";

export function RightPanelContent({
  type,
  panelContent,
  onContentChange,
  role,
}: {
  type: NonNullable<RightPanelType>;
  panelContent: string;
  onContentChange: (content: string) => void;
  role: Role;
}) {
  if (type === "doc-editor") return <ArtifactWorkspace />;
  if (type === "file-preview") return <FilePreviewPanel />;
  if (type === "citations") return <CitationList />;
  if (type === "health-profile") return <HealthProfilePanel />;
  if (type === "settings") return <SettingsPanel />;
  if (type === "help") return <HelpPanel role={role} />;
  if (type === "skills") {
    return (
      <UnavailablePanel
        title="技能在对话区管理"
        description="关闭此面板后继续。"
      />
    );
  }
  if (!panelContent) {
    const emptyCopy = {
      prescription: ["还没有处方报告", "在对话中完成信息收集后生成草案。"],
      cga: ["还没有 CGA 评估报告", "完成评估后可在这里查看报告。"],
      "drug-review": [
        "还没有用药审查报告",
        role === "doctor"
          ? "在对话中录入药物后开始审查。"
          : "在对话中录入药物后查看审查结果。",
      ],
    }[type];
    return emptyCopy ? (
      <UnavailablePanel title={emptyCopy[0]} description={emptyCopy[1]} />
    ) : null;
  }
  return (
    <MarkdownEditor
      value={panelContent}
      onChange={onContentChange}
      className="min-h-0 flex-1"
      readOnly={type === "cga" || role !== "doctor"}
    />
  );
}

function FilePreviewPanel() {
  const [selected, setSelected] = useState<FileTag | null>(null);
  const role = useAppStore((state) => state.role);
  const seniorMode = useAppStore((state) => state.seniorMode);
  const senior = role === "patient" && seniorMode;

  if (!selected) return <FileUpload onFileParsed={setSelected} />;
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
        <button
          type="button"
          onClick={() => setSelected(null)}
          className={cn("text-xs text-primary hover:underline", senior && "min-h-12 text-base")}
        >
          ← 返回上传列表
        </button>
        <span className={cn("max-w-[180px] truncate text-xs text-muted-foreground", senior && "text-base")}>
          {selected.fileName}
        </span>
      </div>
      <div className="min-h-0 flex-1">
        <DocumentPreview file={selected} />
      </div>
    </div>
  );
}

function UnavailablePanel({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  const seniorMode = useAppStore((state) => state.seniorMode);
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
      <div className={cn("font-medium", seniorMode && "text-xl")}>{title}</div>
      <p className={cn("max-w-sm text-sm leading-relaxed text-muted-foreground", seniorMode && "text-base leading-8")}>
        {description}
      </p>
    </div>
  );
}
