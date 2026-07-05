"use client";

import { ShieldAlert } from "lucide-react";
import { EMERGENCY_ALERT, HIGH_RISK_SYMPTOMS } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface EmergencyAlertProps {
  /** 命中的高风险症状列表，未传则展示通用提示 */
  matchedSymptoms?: string[];
  className?: string;
}

/**
 * 高风险症状紧急就医提示
 * 红色警示框，所有高风险症状输出必须附带
 * 对齐 gerclaw设计要求.md §9.2 / 铁律5
 */
export function EmergencyAlert({
  matchedSymptoms,
  className,
}: EmergencyAlertProps) {
  const symptoms =
    matchedSymptoms && matchedSymptoms.length > 0
      ? matchedSymptoms
      : [...HIGH_RISK_SYMPTOMS];

  return (
    <div
      role="alert"
      aria-label="高风险症状紧急就医提示"
      className={cn(
        "flex flex-col gap-1 rounded-lg border border-red-300 bg-red-50 px-3 py-2.5 text-red-800 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200",
        className
      )}
    >
      <div className="flex items-center gap-2">
        <ShieldAlert className="size-5 shrink-0" aria-hidden />
        <p className="text-sm font-semibold leading-relaxed">
          {EMERGENCY_ALERT}
        </p>
      </div>
      <div className="flex flex-wrap gap-1 mt-1">
        <span className="text-xs">高风险症状：</span>
        {symptoms.map((s) => (
          <span
            key={s}
            className="inline-flex items-center rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-medium dark:bg-red-900/40"
          >
            {s}
          </span>
        ))}
      </div>
      <p className="text-xs mt-1">如出现上述症状，请立即拨打 120 或前往就近医院急诊。</p>
    </div>
  );
}
