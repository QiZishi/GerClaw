"use client";

import { RightPanelContent } from "@/components/layout/right-panel/RightPanelContent";
import { RightPanelHeader } from "@/components/layout/right-panel/RightPanelHeader";
import { useRightPanelFrame } from "@/components/layout/right-panel/useRightPanelFrame";
import { LAYOUT } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/appStore";
import { useArtifactStore } from "@/stores/artifactStore";
import type { RightPanelType } from "@/types";

const PANEL_TITLES: Record<NonNullable<RightPanelType>, string> = {
  skills: "技能管理",
  prescription: "五大处方报告",
  cga: "CGA 评估结果",
  "file-preview": "文件预览",
  citations: "引用列表",
  "health-profile": "健康画像",
  "drug-review": "用药审查报告",
  settings: "设置",
  help: "使用教程",
  "doc-editor": "文档产物",
};

export function RightPanel() {
  const open = useAppStore((state) => state.rightPanelOpen);
  const type = useAppStore((state) => state.rightPanelType);
  const role = useAppStore((state) => state.role);
  const seniorMode = useAppStore((state) => state.seniorMode);
  const panelContent = useAppStore((state) => state.panelContent);
  const setPanelContent = useAppStore((state) => state.setPanelContent);
  const closePanel = useAppStore((state) => state.closeRightPanel);
  const frame = useRightPanelFrame(open, Boolean(type));
  const senior = role === "patient" && seniorMode;

  const requestClose = () => {
    if (
      type === "doc-editor" &&
      useArtifactStore.getState().dirty &&
      !window.confirm("文档仍有未保存的修改。确定关闭并放弃这些修改吗？")
    ) {
      return;
    }
    closePanel();
    if (type === "doc-editor") useArtifactStore.getState().clear();
  };

  if (!frame.mounted || !type) return null;
  const transition = frame.isMobile
    ? "transition-transform duration-[var(--motion-panel)] ease-[var(--motion-ease-drawer)]"
    : "transition-opacity duration-[var(--motion-popover)] ease-[var(--motion-ease-out)]";

  return (
    <>
      <div
        className={cn(
          "fixed inset-0 z-30 bg-black/40 transition-opacity xl:hidden",
          frame.visible ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={requestClose}
        aria-hidden
      />
      <aside
        className={cn(
          "fixed right-0 top-0 z-40 flex h-full flex-col overflow-hidden border-l border-border bg-background xl:relative xl:z-auto",
          frame.isMobile ? "w-full" : "shrink-0",
          transition,
          frame.visible
            ? frame.isMobile
              ? "translate-x-0 opacity-100"
              : "opacity-100"
            : frame.isMobile
              ? "translate-x-full opacity-0"
              : "opacity-0",
        )}
        style={{
          width: frame.isMobile ? "100%" : frame.visible ? frame.rightPanelWidth : 0,
          minWidth: frame.isMobile ? "auto" : frame.visible ? frame.rightPanelWidth : 0,
          pointerEvents: frame.visible ? "auto" : "none",
        }}
        aria-label={PANEL_TITLES[type]}
      >
        <div
          onMouseDown={frame.handleResizeStart}
          onKeyDown={frame.handleResizeKeyDown}
          className="absolute bottom-0 left-0 top-0 hidden w-3 cursor-col-resize items-center justify-center hover:bg-primary/10 xl:flex"
          role="separator"
          tabIndex={0}
          aria-orientation="vertical"
          aria-valuemin={LAYOUT.rightPanel.min}
          aria-valuemax={LAYOUT.rightPanel.max}
          aria-valuenow={frame.rightPanelWidth}
          aria-label="调整产物面板宽度"
        >
          <div className="h-12 w-0.5 rounded-full bg-border" />
        </div>
        <RightPanelHeader
          title={PANEL_TITLES[type]}
          type={type}
          content={panelContent}
          senior={senior}
          onClose={requestClose}
        />
        <div className="flex min-h-0 flex-1 flex-col">
          <RightPanelContent
            type={type}
            panelContent={panelContent}
            onContentChange={setPanelContent}
            role={role}
          />
        </div>
      </aside>
    </>
  );
}
