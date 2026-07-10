"use client";

import { WifiOff } from "lucide-react";
import { useAppStore } from "@/stores/appStore";

export function OfflineBanner() {
  const isOnline = useAppStore((s) => s.isOnline);

  if (isOnline) return null;

  return (
    <div className="sticky top-0 z-50 bg-amber-500 text-amber-950 px-4 py-2 flex items-center justify-center gap-2 text-sm font-medium shadow-md">
      <WifiOff className="w-4 h-4" />
      <span>网络已断开，请检查网络连接</span>
    </div>
  );
}
