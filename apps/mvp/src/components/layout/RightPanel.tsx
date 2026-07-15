"use client";

import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { X, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";
import { MarkdownEditor } from "@/components/editor/MarkdownEditor";
import { FileUpload } from "@/components/document/FileUpload";
import { DocumentPreview } from "@/components/document/DocumentPreview";
import { CitationList } from "@/components/search/CitationList";
import { ExportButton } from "@/components/prescription/ExportButton";
import { toast } from "@/components/ui/toast";
import type { FileTag as FileTagData, RightPanelType } from "@/types";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { SettingsPanel } from "@/components/settings/SettingsPanel";

// 注：技能管理（skills）已迁移至中间栏显示，不再占用右侧面板
const PANEL_TITLES: Record<NonNullable<RightPanelType>, string> = {
  skills: "技能管理",
  prescription: "五大处方报告",
  cga: "CGA 评估报告",
  "file-preview": "文件预览",
  citations: "引用列表",
  "health-profile": "健康画像",
  "drug-review": "用药审查报告",
  settings: "设置",
  "doc-editor": "文档编辑",
};

const EXPORTABLE_PANELS: RightPanelType[] = ["prescription", "cga", "drug-review", "doc-editor"];

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
  const panelContent = useAppStore((s) => s.panelContent);
  const setPanelContent = useAppStore((s) => s.setPanelContent);
  const reducedMotion = useReducedMotion();

  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (rightPanelOpen && rightPanelType) {
      const rafId = requestAnimationFrame(() => {
        setMounted(true);
        requestAnimationFrame(() => setVisible(true));
      });
      return () => cancelAnimationFrame(rafId);
    } else if (mounted) {
      const rafId = requestAnimationFrame(() => setVisible(false));
      const timer = setTimeout(() => setMounted(false), reducedMotion ? 0 : 250);
      return () => {
        cancelAnimationFrame(rafId);
        clearTimeout(timer);
      };
    }
  }, [rightPanelOpen, rightPanelType, mounted, reducedMotion]);

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

  const handleCopy = useCallback(async () => {
    if (!panelContent) return;
    try {
      await navigator.clipboard.writeText(panelContent);
      toast.show("已复制");
    } catch {
      toast.show("复制失败");
    }
  }, [panelContent]);

  if (!mounted || !rightPanelType) {
    return null;
  }

  const title = PANEL_TITLES[rightPanelType] ?? "面板";
  const isMobile = typeof window !== "undefined" && window.innerWidth < 768;
  const mobileTransition = reducedMotion ? "" : "transition-transform duration-250 ease-out";
  const desktopTransition = reducedMotion ? "" : "transition-all duration-250 ease-out";
  const opacityTransitionClass = reducedMotion ? "" : "transition-opacity duration-250 ease-out";

  return (
    <>
      {/* 移动端遮罩 */}
      <div
        className={cn(
          "fixed inset-0 z-30 bg-black/40 md:hidden",
          opacityTransitionClass,
          visible ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={closeRightPanel}
        aria-hidden
      />
      <aside
        className={cn(
          "fixed right-0 top-0 z-40 h-full bg-background border-l border-border flex flex-col overflow-hidden",
          "md:relative md:z-auto",
          isMobile ? "w-full" : "shrink-0",
          isMobile
            ? cn(mobileTransition, visible ? "translate-x-0" : "translate-x-full")
            : cn(desktopTransition, visible ? "opacity-100" : "opacity-0")
        )}
        style={{
          width: isMobile
            ? "100%"
            : (visible ? rightPanelWidth : 0),
          minWidth: isMobile ? "auto" : (visible ? rightPanelWidth : 0),
          borderLeftWidth: isMobile ? "" : (visible ? "" : "0px"),
          pointerEvents: visible ? "auto" : "none",
        }}
      >
        {/* 拖拽手柄 */}
        <div
          onMouseDown={handleMouseDown}
          className="absolute left-0 top-0 bottom-0 w-3 cursor-col-resize hover:bg-primary/20 active:bg-primary/30 transition-colors flex items-center justify-center"
          aria-label="拖拽调整宽度"
        >
          <div className="w-0.5 h-12 bg-border rounded-full group-hover:bg-primary/50" />
        </div>

        {/* 头部 */}
        <header className="flex items-center justify-between gap-2 px-4 h-12 shrink-0 border-b border-border">
          <span className="font-medium text-sm">{title}</span>
          <div className="flex items-center gap-1">
            {panelContent && (
              <Button
                variant="ghost"
                size="icon-sm"
                className="btn-icon"
                onClick={handleCopy}
                aria-label="复制内容"
                title="复制 Markdown 源码"
              >
                <Copy className="size-4" />
              </Button>
            )}
            {EXPORTABLE_PANELS.includes(rightPanelType) && panelContent && (
              <ExportButton
                title={title}
                content={panelContent}
                variant="dropdown"
              />
            )}
            <Button
              variant="ghost"
              size="icon-sm"
              className="btn-icon"
              onClick={closeRightPanel}
              aria-label="关闭"
            >
              <X className="size-4" />
            </Button>
          </div>
        </header>

        <Separator />

        <div className="flex-1 min-h-0 flex flex-col">
          <PanelContent
            type={rightPanelType}
            panelContent={panelContent}
            onContentChange={setPanelContent}
          />
        </div>
      </aside>
    </>
  );
}

/** 根据 type 渲染对应面板内容 */
function PanelContent({
  type,
  panelContent,
  onContentChange,
}: {
  type: NonNullable<RightPanelType>;
  panelContent: string;
  onContentChange: (content: string) => void;
}) {
  switch (type) {
    case "skills":
      return (
        <div className="flex-1 min-h-0 overflow-y-auto p-4 flex flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
          技能管理已迁移至中间栏，请点击侧边栏的技能管理按钮。
        </div>
      );

    case "prescription":
      if (panelContent) {
        return (
          <MarkdownEditor
            value={panelContent}
            onChange={onContentChange}
            className="flex-1 min-h-0"
          />
        );
      }
      return (
        <UnavailablePanel
          title="还没有处方报告"
          description="处方工作流尚未接入生产后端。您可以先在对话中描述健康情况，系统不会生成伪报告。"
        />
      );

    case "cga": {
      return (
        <MarkdownEditor
          value={panelContent}
          onChange={onContentChange}
          className="flex-1 min-h-0"
          readOnly={!panelContent}
        />
      );
    }

    case "file-preview":
      return (
        <div className="flex-1 min-h-0 flex flex-col">
          <FilePreviewPanel />
        </div>
      );

    case "citations":
      return (
        <div className="flex-1 min-h-0 flex flex-col">
          <CitationList />
        </div>
      );

    case "health-profile":
      return (
        <div className="flex-1 min-h-0 flex flex-col">
          <HealthProfilePanel />
        </div>
      );

    case "drug-review":
      if (panelContent) {
        return (
          <MarkdownEditor
            value={panelContent}
            onChange={onContentChange}
            className="flex-1 min-h-0"
          />
        );
      }
      return (
        <div className="flex-1 min-h-0 overflow-y-auto p-4">
          <DrugReviewPanel />
        </div>
      );

    case "settings":
      return <SettingsPanel />;

    case "doc-editor":
      return (
        <MarkdownEditor
          value={panelContent}
          onChange={onContentChange}
          className="flex-1 min-h-0"
        />
      );
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

function HealthProfilePanel() {
  return (
    <UnavailablePanel
      title="还没有健康画像"
      description="当前访客身份没有可读取的个人健康档案。真实账号与患者授权将在账号/RBAC 阶段接入。"
    />
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

function UnavailablePanel({ title, description }: { title: string; description: string }) {
  const seniorMode = useAppStore((state) => state.seniorMode);
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
      <div className={cn("font-medium", seniorMode && "text-xl")}>{title}</div>
      <p className={cn("max-w-sm text-sm leading-relaxed text-muted-foreground", seniorMode && "text-base leading-8")}>{description}</p>
    </div>
  );
}
