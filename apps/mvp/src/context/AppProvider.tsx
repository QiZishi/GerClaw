/**
 * 全局应用 Provider 组合
 * 对齐 FRONTEND.md §4 状态管理规范
 * 组合：ThemeProvider + 老年模式 + 角色
 */
"use client";

import { useEffect, type ReactNode } from "react";
import { ThemeProvider } from "./ThemeProvider";
import { useAppStore } from "@/stores/appStore";

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

export function AppProvider({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <SeniorModeApplier />
      <RoleApplier />
      {children}
    </ThemeProvider>
  );
}
