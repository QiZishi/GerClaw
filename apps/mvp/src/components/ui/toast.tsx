"use client";

import { useEffect, useState, useCallback, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

interface ToastItem {
  id: string;
  message: string;
}

let toastListeners: ((item: ToastItem) => void)[] = [];
let toastCounter = 0;

/** 轻量级 toast 工具（无第三方依赖） */
export const toast = {
  show(message: string, duration = 2500) {
    const item: ToastItem = { id: `toast-${++toastCounter}`, message };
    toastListeners.forEach((l) => l(item));
    if (typeof window !== "undefined") {
      window.setTimeout(() => {
        toastListeners = toastListeners;
      }, duration);
    }
  },
};

// 使用 useSyncExternalStore 检测 SSR，避免 useEffect 内 setState 触发级联渲染
const emptySubscribe = () => () => {};
const clientSnapshot = () => true;
const serverSnapshot = () => false;

/** Toast 容器，挂载在应用根部 */
export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>([]);
  const mounted = useSyncExternalStore(
    emptySubscribe,
    clientSnapshot,
    serverSnapshot
  );

  const removeItem = useCallback((id: string) => {
    setItems((prev) => prev.filter((i) => i.id !== id));
  }, []);

  useEffect(() => {
    const listener = (item: ToastItem) => {
      setItems((prev) => [...prev, item]);
      window.setTimeout(() => removeItem(item.id), 2500);
    };
    toastListeners.push(listener);
    return () => {
      toastListeners = toastListeners.filter((l) => l !== listener);
    };
  }, [removeItem]);

  if (!mounted) return null;

  return createPortal(
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[100] flex flex-col items-center gap-2 pointer-events-none">
      {items.map((item) => (
        <div
          key={item.id}
          className="pointer-events-auto rounded-lg bg-foreground text-background px-4 py-2 text-sm shadow-lg animate-in fade-in slide-in-from-bottom-2 duration-200"
        >
          {item.message}
        </div>
      ))}
    </div>,
    document.body
  );
}
