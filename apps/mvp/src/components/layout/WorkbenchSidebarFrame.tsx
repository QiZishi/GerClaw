"use client";

import { useCallback, useEffect, useRef, type KeyboardEvent, type PointerEvent } from "react";
import { PanelLeftOpen, Plus, Stethoscope } from "lucide-react";

import { Sidebar } from "@/components/layout/Sidebar";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { LAYOUT } from "@/lib/constants";
import { sidebarWidthFromKey } from "@/lib/workbench-layout";
import { useAppStore } from "@/stores/appStore";
import { useChatStore } from "@/stores/chatStore";

export function WorkbenchSidebarFrame() {
  const collapsed = useAppStore((state) => state.sidebarCollapsed);
  const width = useAppStore((state) => state.sidebarWidth);
  const role = useAppStore((state) => state.role);
  const seniorMode = useAppStore((state) => state.seniorMode);
  const setCollapsed = useAppStore((state) => state.setSidebarCollapsed);
  const setSidebarWidth = useAppStore((state) => state.setSidebarWidth);
  const setCurrentSession = useAppStore((state) => state.setCurrentSession);
  const createSession = useChatStore((state) => state.createSession);
  const draggingRef = useRef(false);

  const stopDragging = useCallback(() => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);

  useEffect(() => {
    const move = (event: globalThis.PointerEvent) => {
      if (draggingRef.current) setSidebarWidth(event.clientX);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stopDragging);
    window.addEventListener("pointercancel", stopDragging);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stopDragging);
      window.removeEventListener("pointercancel", stopDragging);
      stopDragging();
    };
  }, [setSidebarWidth, stopDragging]);

  const beginDragging = (event: PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    draggingRef.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  const resizeFromKeyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    const nextWidth = sidebarWidthFromKey(width, event.key, event.shiftKey);
    if (nextWidth === null) return;
    event.preventDefault();
    setSidebarWidth(nextWidth);
  };

  if (collapsed) {
    return (
      <nav
        className="hidden h-full shrink-0 flex-col items-center border-r border-sidebar-border bg-sidebar py-2 xl:flex"
        style={{ width: LAYOUT.sidebar.collapsed }}
        aria-label="折叠的会话导航"
      >
        <div className="mb-2 grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground">
          <Stethoscope className="size-5" aria-hidden />
          <span className="sr-only">GerClaw</span>
        </div>
        <RailAction
          label="展开"
          seniorMode={seniorMode}
          onClick={() => setCollapsed(false)}
          icon={<PanelLeftOpen className="size-4" aria-hidden />}
        />
        <RailAction
          label="新建"
          seniorMode={seniorMode}
          onClick={() => setCurrentSession(createSession(role))}
          icon={<Plus className="size-4" aria-hidden />}
        />
      </nav>
    );
  }

  return (
    <div className="relative hidden h-full shrink-0 xl:block" style={{ width }}>
      <Sidebar />
      <div
        role="separator"
        tabIndex={0}
        aria-label="调整会话栏宽度"
        aria-orientation="vertical"
        aria-valuemin={LAYOUT.sidebar.min}
        aria-valuemax={LAYOUT.sidebar.max}
        aria-valuenow={width}
        onPointerDown={beginDragging}
        onKeyDown={resizeFromKeyboard}
        onDoubleClick={() => setSidebarWidth(LAYOUT.sidebar.default)}
        className="absolute inset-y-0 right-0 z-20 w-2 translate-x-1/2 cursor-col-resize touch-none focus-visible:bg-primary/20 focus-visible:outline-none"
        title="拖动调整宽度，双击恢复默认"
      />
    </div>
  );
}

function RailAction({
  label,
  seniorMode,
  onClick,
  icon,
}: {
  label: string;
  seniorMode: boolean;
  onClick: () => void;
  icon: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            className="mb-1 h-auto min-h-12 w-12 flex-col gap-0.5 px-1 py-1.5"
            onClick={onClick}
            aria-label={label}
          />
        }
      >
        {icon}
        {seniorMode && <span className="text-base leading-none">{label}</span>}
      </TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}
