"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
} from "react";
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
import { HealthProfilePanel } from "@/components/health/HealthProfilePanel";
import { LAYOUT } from "@/lib/constants";

const PANEL_TITLES: Record<NonNullable<RightPanelType>, string> = {
  skills: "技能管理",
  prescription: "五大处方报告",
  cga: "CGA 评估结果",
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
  const role = useAppStore((s) => s.role);
  const seniorMode = useAppStore((s) => s.seniorMode);
  const rightPanelType = useAppStore((s) => s.rightPanelType);
  const rightPanelWidth = useAppStore((s) => s.rightPanelWidth);
  const closeRightPanel = useAppStore((s) => s.closeRightPanel);
  const setRightPanelWidth = useAppStore((s) => s.setRightPanelWidth);
  const panelContent = useAppStore((s) => s.panelContent);
  const setPanelContent = useAppStore((s) => s.setPanelContent);
  const reducedMotion = useReducedMotion();
  const isSeniorPatient = role === "patient" && seniorMode;

  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);
  const [isNarrowViewport, setIsNarrowViewport] = useState(true);

  useEffect(() => {
    const syncViewportMode = () => setIsNarrowViewport(window.innerWidth < 1280);
    syncViewportMode();
    window.addEventListener("resize", syncViewportMode);
    return () => window.removeEventListener("resize", syncViewportMode);
  }, []);

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

  const handleResizeKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      const step = event.shiftKey ? 48 : 16;
      let nextWidth: number | null = null;
      if (event.key === "ArrowLeft") nextWidth = rightPanelWidth + step;
      if (event.key === "ArrowRight") nextWidth = rightPanelWidth - step;
      if (event.key === "Home") nextWidth = LAYOUT.rightPanel.min;
      if (event.key === "End") nextWidth = LAYOUT.rightPanel.max;
      if (nextWidth === null) return;
      event.preventDefault();
      setRightPanelWidth(nextWidth);
    },
    [rightPanelWidth, setRightPanelWidth]
  );

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
  const isMobile = isNarrowViewport;
  const mobileTransition = reducedMotion ? "" : "transition-transform duration-250 ease-out";
  const desktopTransition = reducedMotion ? "" : "transition-all duration-250 ease-out";
  const opacityTransitionClass = reducedMotion ? "" : "transition-opacity duration-250 ease-out";

  return (
    <>
      {/* 移动端遮罩 */}
      <div
        className={cn(
          "fixed inset-0 z-30 bg-black/40 xl:hidden",
          opacityTransitionClass,
          visible ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={closeRightPanel}
        aria-hidden
      />
      <aside
        className={cn(
          "fixed right-0 top-0 z-40 h-full bg-background border-l border-border flex flex-col overflow-hidden",
          "xl:relative xl:z-auto",
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
          onKeyDown={handleResizeKeyDown}
          className="absolute left-0 top-0 bottom-0 hidden w-3 cursor-col-resize items-center justify-center transition-colors hover:bg-primary/20 active:bg-primary/30 xl:flex"
          role="separator"
          tabIndex={0}
          aria-orientation="vertical"
          aria-valuemin={LAYOUT.rightPanel.min}
          aria-valuemax={LAYOUT.rightPanel.max}
          aria-valuenow={rightPanelWidth}
          aria-label="拖拽调整宽度"
        >
          <div className="w-0.5 h-12 bg-border rounded-full group-hover:bg-primary/50" />
        </div>

        {/* 头部 */}
        <header className={cn("flex items-center justify-between gap-2 px-4 h-12 shrink-0 border-b border-border", isSeniorPatient && "h-16")}>
          <span className={cn("font-medium text-sm", isSeniorPatient && "text-lg")}>{title}</span>
          <div className="flex items-center gap-1">
            {panelContent && (
              <Button
                variant="ghost"
                size={isSeniorPatient ? "default" : "icon-sm"}
                className={cn("btn-icon", isSeniorPatient && "min-h-12 gap-2 px-3 text-base")}
                onClick={handleCopy}
                aria-label="复制内容"
                title="复制 Markdown 源码"
              >
                <Copy className="size-4" />
                {isSeniorPatient && <span>复制</span>}
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
              size={isSeniorPatient ? "default" : "icon-sm"}
              className={cn("btn-icon", isSeniorPatient && "min-h-12 gap-2 px-3 text-base")}
              onClick={closeRightPanel}
              aria-label="关闭"
            >
              <X className="size-4" />
              {isSeniorPatient && <span>关闭</span>}
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
          <p className="font-medium text-foreground">在对话主区管理临床技能</p>
          <p className="leading-6">请关闭此面板后，点击左侧的“技能”继续选择、审阅或创建工作流。</p>
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
          description="请先在对话区启动“五大处方信息收集”，按步骤保存健康信息。医学规则、医生审核和患者授权齐备后，系统才会在这里展示可导出的报告；不会用示例内容代替真实结果。"
        />
      );

    case "cga": {
      if (!panelContent) {
        return (
          <UnavailablePanel
            title="还没有 CGA 评估报告"
            description="完成真实的综合老年评估后，报告才会显示在这里；当前不会用示例内容代替评估结果。"
          />
        );
      }
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
        <UnavailablePanel
          title="还没有用药审查报告"
          description="请先在对话区启动“用药信息收集”并保存所需信息。医学规则、医生审核和患者授权齐备后，结果才会显示在这里；不会使用示例结果代替。"
        />
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
  const role = useAppStore((state) => state.role);
  const seniorMode = useAppStore((state) => state.seniorMode);
  const isSeniorPatient = role === "patient" && seniorMode;

  if (selected) {
    return (
      <div className="flex flex-col h-full">
        <div className="px-3 py-1.5 border-b border-border flex items-center justify-between">
          <button
            type="button"
            onClick={() => setSelected(null)}
            className={cn("text-xs text-primary hover:underline", isSeniorPatient && "min-h-12 text-base")}
          >
            ← 返回上传列表
          </button>
          <span className={cn("text-xs text-muted-foreground truncate max-w-[180px]", isSeniorPatient && "text-base")}>
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

function UnavailablePanel({ title, description }: { title: string; description: string }) {
  const seniorMode = useAppStore((state) => state.seniorMode);
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
      <div className={cn("font-medium", seniorMode && "text-xl")}>{title}</div>
      <p className={cn("max-w-sm text-sm leading-relaxed text-muted-foreground", seniorMode && "text-base leading-8")}>{description}</p>
    </div>
  );
}
