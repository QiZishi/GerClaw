/**
 * localStorage 封装
 * 对齐 ARCHITECTURE.md §6 数据边界（读取时 try-catch+schema 校验，损坏时清除）
 */

const PREFIX = "gerclaw:";

export const storage = {
  get<T>(key: string, fallback: T): T {
    if (typeof window === "undefined") return fallback;
    try {
      const raw = window.localStorage.getItem(PREFIX + key);
      if (raw === null) return fallback;
      return JSON.parse(raw) as T;
    } catch (err) {
      console.warn(`[storage] 读取 ${key} 失败，清除损坏数据：`, err);
      window.localStorage.removeItem(PREFIX + key);
      return fallback;
    }
  },

  set<T>(key: string, value: T): void {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
    } catch (err) {
      console.warn(`[storage] 写入 ${key} 失败：`, err);
    }
  },

  remove(key: string): void {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(PREFIX + key);
  },

  clear(): void {
    if (typeof window === "undefined") return;
    Object.keys(window.localStorage)
      .filter((k) => k.startsWith(PREFIX))
      .forEach((k) => window.localStorage.removeItem(k));
  },
};

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
