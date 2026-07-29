import { LAYOUT } from "./constants.ts";

export function clampSidebarWidth(width: number): number {
  if (!Number.isFinite(width)) return LAYOUT.sidebar.default;
  return Math.max(LAYOUT.sidebar.min, Math.min(LAYOUT.sidebar.max, Math.round(width)));
}

export function sidebarWidthFromKey(
  currentWidth: number,
  key: string,
  shiftKey = false,
): number | null {
  const step = shiftKey ? 48 : 16;
  if (key === "ArrowLeft") return clampSidebarWidth(currentWidth - step);
  if (key === "ArrowRight") return clampSidebarWidth(currentWidth + step);
  if (key === "Home") return LAYOUT.sidebar.min;
  if (key === "End") return LAYOUT.sidebar.max;
  return null;
}
