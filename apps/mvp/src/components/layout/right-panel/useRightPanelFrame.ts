"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
} from "react";

import { LAYOUT } from "@/lib/constants";
import { useAppStore } from "@/stores/appStore";

export function useRightPanelFrame(open: boolean, hasType: boolean) {
  const rightPanelWidth = useAppStore((state) => state.rightPanelWidth);
  const setRightPanelWidth = useAppStore((state) => state.setRightPanelWidth);
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);
  const [isMobile, setIsMobile] = useState(true);
  const draggingRef = useRef(false);

  useEffect(() => {
    const syncViewport = () => setIsMobile(window.innerWidth < 1280);
    syncViewport();
    window.addEventListener("resize", syncViewport);
    return () => window.removeEventListener("resize", syncViewport);
  }, []);

  useEffect(() => {
    if (open && hasType) {
      const frame = requestAnimationFrame(() => {
        setMounted(true);
        requestAnimationFrame(() => setVisible(true));
      });
      return () => cancelAnimationFrame(frame);
    }
    if (!mounted) return;
    const frame = requestAnimationFrame(() => setVisible(false));
    const timer = window.setTimeout(() => setMounted(false), 250);
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [hasType, mounted, open]);

  const handleResizeStart = useCallback((event: MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    draggingRef.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  const handleResizeKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      const step = event.shiftKey ? 48 : 16;
      const widthByKey: Record<string, number> = {
        ArrowLeft: rightPanelWidth + step,
        ArrowRight: rightPanelWidth - step,
        Home: LAYOUT.rightPanel.min,
        End: LAYOUT.rightPanel.max,
      };
      const nextWidth = widthByKey[event.key];
      if (nextWidth === undefined) return;
      event.preventDefault();
      setRightPanelWidth(nextWidth);
    },
    [rightPanelWidth, setRightPanelWidth],
  );

  useEffect(() => {
    const resize = (event: globalThis.MouseEvent) => {
      if (draggingRef.current) setRightPanelWidth(window.innerWidth - event.clientX);
    };
    const stopResize = () => {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", resize);
    window.addEventListener("mouseup", stopResize);
    return () => {
      window.removeEventListener("mousemove", resize);
      window.removeEventListener("mouseup", stopResize);
      stopResize();
    };
  }, [setRightPanelWidth]);

  return {
    mounted,
    visible,
    isMobile,
    rightPanelWidth,
    handleResizeStart,
    handleResizeKeyDown,
  };
}
