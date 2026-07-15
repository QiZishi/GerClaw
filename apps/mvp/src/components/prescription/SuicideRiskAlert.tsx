"use client";

import { AlertTriangle, Phone } from "lucide-react";
import { cn } from "@/lib/utils";

interface SuicideRiskAlertProps {
  className?: string;
  onDismiss?: () => void;
}

export function SuicideRiskAlert({ className, onDismiss }: SuicideRiskAlertProps) {
  return (
    <div
      role="alert"
      aria-label="自杀风险紧急提示"
      className={cn(
        "flex flex-col gap-2 rounded-lg border-2 border-red-600 bg-red-600 px-4 py-4 text-white shadow-lg",
        className
      )}
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="size-7 shrink-0 mt-0.5" aria-hidden />
        <div className="flex-1">
          <p className="text-lg font-bold leading-tight">
            ⚠️ 自杀风险预警
          </p>
          <p className="mt-2 text-base leading-relaxed">
            您在评估中提到了伤害自己的想法，这非常重要，请您：
          </p>
          <ul className="mt-2 space-y-1.5 text-base list-disc pl-5">
            <li>立即告诉身边的家人、朋友或医生</li>
            <li>不要独处，确保有人陪伴</li>
            <li>请立即拨打心理危机干预热线</li>
          </ul>
        </div>
      </div>
      
      <div className="mt-2 rounded-lg bg-red-700/70 p-3">
        <div className="flex items-center gap-2 mb-2">
          <Phone className="size-5 shrink-0" />
          <span className="font-semibold">24小时心理危机干预热线：</span>
        </div>
        <div className="space-y-1 pl-7">
          <p className="text-lg font-bold">全国心理援助热线：<span className="text-yellow-200">400-161-9995</span></p>
          <p className="text-base">北京心理危机研究与干预中心：<span className="text-yellow-200">010-82951332</span></p>
        </div>
      </div>
      
      <p className="mt-1 text-sm font-semibold text-yellow-100">
        建议您立即前往附近医院精神科/心理科就诊，不要等待！
      </p>
      
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="mt-1 min-h-12 self-end rounded-md px-3 text-base text-red-100 underline underline-offset-4 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-red-600"
        >
          我已知晓
        </button>
      )}
    </div>
  );
}
