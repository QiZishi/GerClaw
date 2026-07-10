/**
 * 全局应用 Provider 组合
 * 对齐 FRONTEND.md §4 状态管理规范
 * 组合：ThemeProvider + 老年模式 + 角色 + 网络状态监听
 */
"use client";

import dynamic from "next/dynamic";
import { useEffect, type ReactNode } from "react";
import { ThemeProvider } from "./ThemeProvider";
import { useAppStore } from "@/stores/appStore";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { toast } from "@/components/ui/toast";

const OfflineBanner = dynamic(
  () => import("@/components/OfflineBanner").then((m) => m.OfflineBanner),
  { ssr: false }
);

/** 老年模式 class 应用器：在 <html> 上添加 senior class */
function SeniorModeApplier() {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const role = useAppStore((s) => s.role);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const root = document.documentElement;
    const enabled = seniorMode && role === "patient";
    if (enabled) {
      root.classList.add("senior-mode");
      root.setAttribute("data-senior", "true");
    } else {
      root.classList.remove("senior-mode");
      root.removeAttribute("data-senior");
    }
  }, [seniorMode, role]);

  return null;
}

/** 角色应用器：在 <html> 上设置 data-role 属性，便于 CSS 区分患者/医生端 */
function RoleApplier() {
  const role = useAppStore((s) => s.role);
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.setAttribute("data-role", role);
  }, [role]);
  return null;
}

/** 网络状态监听器 */
function NetworkStatusListener() {
  const setIsOnline = useAppStore((s) => s.setIsOnline);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const handleOnline = () => {
      setIsOnline(true);
      toast.show("网络已恢复连接");
    };
    const handleOffline = () => {
      setIsOnline(false);
    };

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    setIsOnline(navigator.onLine);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [setIsOnline]);

  return null;
}

/** localStorage 可用性检测 */
function StorageAvailabilityChecker() {
  const setStorageFull = useAppStore((s) => s.setStorageFull);

  useEffect(() => {
    if (typeof window === "undefined") return;

    try {
      const testKey = "__gerclaw_storage_test__";
      window.localStorage.setItem(testKey, "1");
      window.localStorage.removeItem(testKey);
    } catch {
      setStorageFull(true);
    }
  }, [setStorageFull]);

  return null;
}

export function AppProvider({ children }: { children: ReactNode }) {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <SeniorModeApplier />
        <RoleApplier />
        <NetworkStatusListener />
        <StorageAvailabilityChecker />
        <OfflineBanner />
        {children}
      </ThemeProvider>
    </ErrorBoundary>
  );
}
