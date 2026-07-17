"use client";

import { useEffect, useState, useCallback, useRef, useSyncExternalStore } from "react";
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
const activeToastByMessage = new Map<string, { id: string; expiresAt: number }>();

function clearActiveToast(id: string) {
  for (const [message, activeToast] of activeToastByMessage) {
    if (activeToast.id === id) {
      activeToastByMessage.delete(message);
      return;
    }
  }
}

/** 轻量级 toast 工具（无第三方依赖） */
export const toast = {
  show(message: string, duration?: number) {
    const readableDuration = duration ?? Math.max(4500, Math.min(8000, message.length * 120));
    const now = Date.now();
    const activeToast = activeToastByMessage.get(message);
    const id = activeToast && activeToast.expiresAt > now
      ? activeToast.id
      : `toast-${++toastCounter}`;
    activeToastByMessage.set(message, { id, expiresAt: now + readableDuration });
    const item: ToastItem = { id, message, duration: readableDuration };
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
  const timersRef = useRef(new Map<string, number>());
  const seniorMode = useAppStore((state) => state.seniorMode);
  const mounted = useSyncExternalStore(
    emptySubscribe,
    clientSnapshot,
    serverSnapshot
  );

  const removeItem = useCallback((id: string) => {
    const timer = timersRef.current.get(id);
    if (timer) window.clearTimeout(timer);
    timersRef.current.delete(id);
    clearActiveToast(id);
    setItems((prev) => prev.filter((i) => i.id !== id));
  }, []);

  useEffect(() => {
    const timers = timersRef.current;
    const listener = (item: ToastItem) => {
      // A stack of success messages can cover the action the user has just
      // completed, especially on a 390px screen.  Keep one current status
      // message instead of asking users to dismiss older, superseded notices.
      timers.forEach((timer) => window.clearTimeout(timer));
      timers.clear();
      activeToastByMessage.clear();
      setItems([item]);
      timers.set(
        item.id,
        window.setTimeout(() => removeItem(item.id), item.duration)
      );
    };
    toastListeners.push(listener);
    return () => {
      toastListeners = toastListeners.filter((l) => l !== listener);
      timers.forEach((timer) => window.clearTimeout(timer));
      timers.clear();
    };
  }, [removeItem]);

  if (!mounted) return null;

  return createPortal(
    <div
      className="pointer-events-none fixed bottom-6 left-1/2 z-[100] flex w-[calc(100vw-2rem)] max-w-2xl -translate-x-1/2 flex-col items-stretch gap-2 sm:items-center"
      aria-live="polite"
    >
      {items.map((item) => (
        <div
          key={item.id}
          role="status"
          className={cn(
            "pointer-events-auto flex w-full min-w-0 max-w-full items-center gap-3 rounded-lg bg-foreground px-4 py-3 text-base text-background shadow-lg animate-in fade-in slide-in-from-bottom-2 duration-200 sm:w-fit",
            seniorMode && "text-lg"
          )}
        >
          <span className="min-w-0 flex-1 break-words">{item.message}</span>
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
