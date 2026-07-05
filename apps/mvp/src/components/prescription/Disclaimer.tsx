"use client";

import { AlertTriangle } from "lucide-react";
import { MEDICAL_DISCLAIMER } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface DisclaimerProps {
  /** 自定义文案，默认使用 constants.MEDICAL_DISCLAIMER */
  text?: string;
  className?: string;
}

/**
 * §9.2 医疗免责声明组件
 * 黄色警示框，所有医疗输出必须附带
 */
export function Disclaimer({ text, className }: DisclaimerProps) {
  return (
    <div
      role="note"
      aria-label="医疗免责声明"
      className={cn(
        "flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200",
        className
      )}
    >
      <AlertTriangle className="size-4 shrink-0 mt-0.5" aria-hidden />
      <p className="text-xs leading-relaxed">{text ?? MEDICAL_DISCLAIMER}</p>
    </div>
  );
}
