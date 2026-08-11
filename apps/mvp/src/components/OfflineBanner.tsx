"use client";

import { WifiOff } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/appStore";

export function OfflineBanner() {
  const isOnline = useAppStore((s) => s.isOnline);
  const seniorMode = useAppStore((s) => s.seniorMode);

  if (isOnline) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      data-testid="offline-banner"
      className={cn(
        "sticky top-0 z-50 flex min-h-11 items-center justify-center gap-2 bg-amber-500 px-4 py-2 text-sm font-medium text-amber-950 shadow-md",
        seniorMode && "min-h-12 text-lg",
      )}
    >
      <WifiOff className={cn("size-4", seniorMode && "size-5")} aria-hidden />
      <span>网络已断开，请检查网络连接</span>
    </div>
  );
}
