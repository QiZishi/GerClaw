"use client";

import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import { PrescriptionEntry } from "@/components/prescription/PrescriptionEntry";
import { ScaleSelector } from "@/components/cga/ScaleSelector";
import { CGAReport } from "@/components/cga/CGAReport";
import { FileUpload } from "@/components/document/FileUpload";
import { DocumentPreview } from "@/components/document/DocumentPreview";
import { CitationList } from "@/components/search/CitationList";
import { mockScales, mockCGAReport } from "@/data/mock/cga";
import { mockPatientSummary } from "@/data/mock/prescription";
import type { FileTag as FileTagData, RightPanelType } from "@/types";

// 注：技能管理（skills）已迁移至中间栏显示，不再占用右侧面板
const PANEL_TITLES: Record<NonNullable<RightPanelType>, string> = {
  skills: "技能管理",
  prescription: "处方预览",
  cga: "CGA 评估",
  "file-preview": "文件预览",
  citations: "引用列表",
  "health-profile": "健康画像",
  "drug-review": "用药审查",
  settings: "设置",
};

/**
 * §3.5 右侧动态面板
 * 默认隐藏，展开时 384px，可拖拽 320-500px
 * 根据 rightPanelType 渲染对应功能组件
 */
export function RightPanel() {
  const rightPanelOpen = useAppStore((s) => s.rightPanelOpen);
  const rightPanelType = useAppStore((s) => s.rightPanelType);
  const rightPanelWidth = useAppStore((s) => s.rightPanelWidth);
  const closeRightPanel = useAppStore((s) => s.closeRightPanel);
  const setRightPanelWidth = useAppStore((s) => s.setRightPanelWidth);

  const draggingRef = useRef(false);

  const handleMouseDown = useCallback((e: MouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    draggingRef.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  useEffect(() => {
    const handleMouseMove = (e: globalThis.MouseEvent) => {
      if (!draggingRef.current) return;
      const newWidth = window.innerWidth - e.clientX;
      setRightPanelWidth(newWidth);
    };
    const handleMouseUp = () => {
      if (draggingRef.current) {
        draggingRef.current = false;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }
    };
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [setRightPanelWidth]);

  if (!rightPanelOpen || !rightPanelType) {
    return null;
  }

  const title = PANEL_TITLES[rightPanelType] ?? "面板";

  return (
    <>
      {/* 移动端遮罩 */}
      <div
        className="fixed inset-0 z-30 bg-black/40 md:hidden"
        onClick={closeRightPanel}
        aria-hidden
      />
      <aside
        className={cn(
          "fixed md:relative right-0 top-0 z-40 md:z-auto h-full bg-background border-l border-border flex flex-col",
          "w-full md:w-auto"
        )}
        style={{
          width: typeof window !== "undefined" && window.innerWidth < 768
            ? "100%"
            : rightPanelWidth,
        }}
      >
        {/* 拖拽手柄 */}
        <div
          onMouseDown={handleMouseDown}
          className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-primary/30 transition-colors"
          aria-label="拖拽调整宽度"
        />

        {/* 头部 */}
        <header className="flex items-center justify-between gap-2 px-4 h-12 shrink-0 border-b border-border">
          <span className="font-medium text-sm">{title}</span>
          <Button
            variant="ghost"
            size="icon-sm"
            className="btn-icon"
            onClick={closeRightPanel}
            aria-label="关闭"
          >
            <X className="size-4" />
          </Button>
        </header>

        <Separator />

        {/* 内容（可二次编辑：所有结果文字支持 contentEditable）*/}
        <div
          className="flex-1 min-h-0 overflow-y-auto"
          contentEditable
          suppressContentEditableWarning
          aria-label="结果内容（可编辑）"
          title="可直接编辑文字内容"
        >
          <PanelContent type={rightPanelType} />
        </div>
      </aside>
    </>
  );
}

/** 根据 type 渲染对应面板内容 */
function PanelContent({ type }: { type: NonNullable<RightPanelType> }) {
  switch (type) {
    case "skills":
      // 技能管理已迁移到中间栏，右侧面板不再处理此类型
      return (
        <div className="flex flex-col items-center justify-center gap-2 h-full text-center p-4 text-sm text-muted-foreground">
          技能管理已迁移至中间栏，请点击侧边栏的技能管理按钮。
        </div>
      );

    case "prescription":
      return <PrescriptionEntry initialStage="done" />;

    case "cga":
      return (
        <div className="flex flex-col h-full">
          <ScaleSelector scales={mockScales} />
          <Separator />
          <div className="flex-1 min-h-0 overflow-y-auto">
            <CGAReport report={mockCGAReport} />
          </div>
        </div>
      );

    case "file-preview":
      return <FilePreviewPanel />;

    case "citations":
      return <CitationList />;

    case "health-profile":
      return <HealthProfilePanel />;

    case "drug-review":
      return <DrugReviewPanel />;

    case "settings":
      return <SettingsPlaceholder />;
  }
}

/** 文件预览面板：上传 + 选中后切换到预览 */
function FilePreviewPanel() {
  const [selected, setSelected] = useState<FileTagData | null>(null);

  if (selected) {
    return (
      <div className="flex flex-col h-full">
        <div className="px-3 py-1.5 border-b border-border flex items-center justify-between">
          <button
            type="button"
            onClick={() => setSelected(null)}
            className="text-xs text-primary hover:underline"
          >
            ← 返回上传列表
          </button>
          <span className="text-xs text-muted-foreground truncate max-w-[180px]">
            {selected.fileName}
          </span>
        </div>
        <div className="flex-1 min-h-0">
          <DocumentPreview file={selected} />
        </div>
      </div>
    );
  }

  return <FileUpload onFileParsed={(f) => setSelected(f)} />;
}

/** 健康画像面板：mock 患者基本信息 */
function HealthProfilePanel() {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const p = mockPatientSummary;
  return (
    <div className="flex flex-col h-full overflow-y-auto p-3 space-y-3">
      <header className="flex items-center gap-2">
        <div className="flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary">
          <span className="text-base font-semibold">
            {p.name?.slice(0, 1) ?? "?"}
          </span>
        </div>
        <div>
          <div className={cn("font-medium", seniorMode ? "text-base" : "text-sm")}>
            {p.name ?? "未命名"}
          </div>
          <div className="text-xs text-muted-foreground">
            {p.gender === "female" ? "女" : "男"} · {p.age ?? "?"} 岁
          </div>
        </div>
      </header>

      <section>
        <h4 className="text-xs font-semibold text-muted-foreground uppercase mb-1.5">
          主诉
        </h4>
        <p className={cn("text-sm leading-relaxed", seniorMode && "text-base")}>
          {p.chiefComplaint ?? "—"}
        </p>
      </section>

      <section>
        <h4 className="text-xs font-semibold text-muted-foreground uppercase mb-1.5">
          病史
        </h4>
        <ul className="space-y-1">
          {(p.history ?? []).map((h) => (
            <li key={h} className="text-xs flex items-start gap-1.5">
              <span className="text-primary mt-0.5">•</span>
              <span>{h}</span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h4 className="text-xs font-semibold text-muted-foreground uppercase mb-1.5">
          当前用药
        </h4>
        <ul className="space-y-1">
          {(p.currentMedications ?? []).map((m) => (
            <li
              key={m}
              className="text-xs rounded-md border border-border bg-card px-2 py-1"
            >
              {m}
            </li>
          ))}
        </ul>
      </section>

      {p.allergies && p.allergies.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase mb-1.5">
            过敏史
          </h4>
          <div className="flex flex-wrap gap-1">
            {p.allergies.map((a) => (
              <span
                key={a}
                className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-300"
              >
                {a}
              </span>
            ))}
          </div>
        </section>
      )}

      {p.vitals && Object.keys(p.vitals).length > 0 && (
        <section>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase mb-1.5">
            生命体征
          </h4>
          <div className="grid grid-cols-2 gap-1.5">
            {Object.entries(p.vitals).map(([k, v]) => (
              <div
                key={k}
                className="rounded-md border border-border bg-muted/30 px-2 py-1.5"
              >
                <div className="text-[11px] text-muted-foreground">{k}</div>
                <div className="text-sm font-medium">{v}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="rounded-md border border-amber-200 bg-amber-50 dark:border-amber-900/40 dark:bg-amber-950/30 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
        内容由 AI 生成，仅供参考。身体不适请及时就医。
      </div>
    </div>
  );
}

/** 用药审查结果面板（医生端专用，Phase 2 提供真实数据） */
function DrugReviewPanel() {
  return (
    <div className="p-3 space-y-3">
      <div className="rounded-md border border-border bg-muted/30 p-3 text-sm text-muted-foreground space-y-2">
        <div className="font-medium text-foreground">用药审查结果</div>
        <div>正在对接真实处方审查引擎，Phase 2 将支持：</div>
        <ul className="list-disc pl-4 space-y-1 text-xs">
          <li>药物相互作用（DDI）检测</li>
          <li>老年患者 Beers 标准不合理用药筛查</li>
          <li>重复用药、剂量异常、禁忌症提醒</li>
          <li>肾功能/肝功能相关剂量调整建议</li>
        </ul>
      </div>
      <div className="rounded-md border border-amber-200 bg-amber-50 dark:border-amber-900/40 dark:bg-amber-950/30 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
        AI 审查结果仅供参考，最终处方权归执业医生所有。
      </div>
    </div>
  );
}

/** 设置面板占位（Phase 6 提供） */
function SettingsPlaceholder() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 h-full text-center p-4">
      <div className="text-sm text-muted-foreground">
        设置面板将在 Phase 6 提供
      </div>
      <div className="text-xs text-muted-foreground">
        包含：模型配置、API Key、主题、字号等
      </div>
    </div>
  );
}

