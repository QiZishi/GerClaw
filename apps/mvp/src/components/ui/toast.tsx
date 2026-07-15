"use client";

import { useEffect, useState, useCallback, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";

interface ToastItem {
  id: string;
  message: string;
  duration: number;
}

let toastListeners: ((item: ToastItem) => void)[] = [];
let toastCounter = 0;

/** 轻量级 toast 工具（无第三方依赖） */
export const toast = {
  show(message: string, duration?: number) {
    const readableDuration = duration ?? Math.max(4500, Math.min(8000, message.length * 120));
    const item: ToastItem = { id: `toast-${++toastCounter}`, message, duration: readableDuration };
    toastListeners.forEach((l) => l(item));
  },
};

// 使用 useSyncExternalStore 检测 SSR，避免 useEffect 内 setState 触发级联渲染
const emptySubscribe = () => () => {};
const clientSnapshot = () => true;
const serverSnapshot = () => false;

/** Toast 容器，挂载在应用根部 */
export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seniorMode = useAppStore((state) => state.seniorMode);
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
      window.setTimeout(() => removeItem(item.id), item.duration);
    };
    toastListeners.push(listener);
    return () => {
      toastListeners = toastListeners.filter((l) => l !== listener);
    };
  }, [removeItem]);

  if (!mounted) return null;

  return createPortal(
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[100] flex max-w-[min(92vw,42rem)] flex-col items-center gap-2 pointer-events-none" aria-live="polite">
      {items.map((item) => (
        <div
          key={item.id}
          role="status"
          className={cn(
            "pointer-events-auto flex items-center gap-3 rounded-lg bg-foreground text-background px-4 py-3 text-base shadow-lg animate-in fade-in slide-in-from-bottom-2 duration-200",
            seniorMode && "text-lg"
          )}
        >
          <span className="min-w-0 flex-1">{item.message}</span>
          <button
            type="button"
            className={cn(
              "inline-flex min-h-11 shrink-0 items-center gap-1 rounded-md px-2 hover:bg-background/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-background",
              seniorMode && "min-h-12 px-3 text-base"
            )}
            onClick={() => removeItem(item.id)}
            aria-label="关闭提示"
          >
            <X className="size-4" />
            <span>关闭</span>
          </button>
        </div>
      ))}
    </div>,
    document.body
  );
}
