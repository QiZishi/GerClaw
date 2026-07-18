/**
 * localStorage 封装
 * 对齐 ARCHITECTURE.md §6 数据边界（读取时 try-catch+schema 校验，损坏时清除）
 */

/** 存储 key 常量 */
export const STORAGE_KEYS = {
  theme: "theme",
  role: "role",
  seniorMode: "senior-mode",
  sidebarCollapsed: "sidebar-collapsed",
  rightPanelWidth: "right-panel-width",
  sessions: "sessions",
  messages: "messages",
} as const;
