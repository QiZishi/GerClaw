"use client";
import { AlertTriangle } from "lucide-react";

import { cn } from "@/lib/utils";

export function EmergencyWarningCard({
  message,
  seniorMode,
}: {
  message: string;
  seniorMode: boolean;
}) {
  const displayMessage = message.replace(/^\s*⚠️\s*/, "");
  return (
    <section
      aria-label="紧急医疗警告"
      role="alert"
      className={cn(
        "rounded-xl border-2 border-red-200 bg-red-700 p-4 text-white shadow-sm",
        seniorMode && "p-5",
      )}
    >
      <div className={cn("flex items-center gap-2 font-bold", seniorMode ? "text-xl" : "text-lg")}>
        <AlertTriangle aria-hidden className={seniorMode ? "size-6" : "size-5"} />
        <span>紧急医疗警告</span>
      </div>
      <p className={cn("mt-3 font-medium leading-relaxed", seniorMode ? "text-lg" : "text-base")}>
        {displayMessage}
      </p>
    </section>
  );
}

export function IncompleteAnswerWarning({
  seniorMode,
}: {
  seniorMode: boolean;
}) {
  return (
    <section
      role="alert"
      aria-label="回答未完成提醒"
      className={cn(
        "w-full rounded-xl border border-border bg-muted/30 px-4 py-3 text-foreground",
        seniorMode && "p-4",
      )}
    >
      <p className={cn("leading-relaxed", seniorMode ? "text-lg" : "text-sm")}>
        这次回答没有完整生成
      </p>
    </section>
  );
}

export function AssistantRunStatus({
  phase,
  seniorMode,
}: {
  phase: string;
  seniorMode: boolean;
}) {
  return (
    <div
      className={cn(
        "flex w-full flex-wrap items-center gap-2 rounded-xl border border-primary/20 bg-primary/5 px-3 py-2 text-primary",
        seniorMode ? "min-h-12 text-base" : "text-sm",
      )}
    >
      <span className="inline-flex items-center gap-2 whitespace-nowrap" role="status">
        <span className="codex-activity-dots" aria-hidden>
          <span className="codex-activity-dot" />
          <span className="codex-activity-dot" />
          <span className="codex-activity-dot" />
        </span>
        <span className="font-medium">{phase}</span>
      </span>
    </div>
  );
}
