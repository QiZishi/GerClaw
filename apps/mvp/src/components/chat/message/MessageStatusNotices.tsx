"use client";

import { useEffect, useState } from "react";
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
  companionMode,
}: {
  seniorMode: boolean;
  companionMode: boolean;
}) {
  return (
    <section
      role="alert"
      aria-label="回答未完成提醒"
      className={cn(
        "w-full rounded-xl border-2 border-amber-400 bg-amber-50 px-4 py-3 text-amber-950 shadow-sm dark:border-amber-500 dark:bg-amber-950/30 dark:text-amber-100",
        seniorMode && "p-4",
      )}
    >
      <div className={cn("flex items-center gap-2 font-bold", seniorMode ? "text-lg" : "text-base")}>
        <AlertTriangle aria-hidden className={cn("shrink-0", seniorMode ? "size-6" : "size-5")} />
        <span>本次回复未完成</span>
      </div>
      <p className={cn("mt-2 leading-relaxed", seniorMode ? "text-lg" : "text-sm")}>
        {companionMode
          ? "以下内容未经最终安全校验。您可以重新生成，或稍后再试。"
          : "以下内容未经最终安全校验，请勿据此调整治疗或用药。您可以重新生成，或咨询医生。"}
      </p>
    </section>
  );
}

function formatElapsedTime(elapsedMs: number): string {
  const elapsedSeconds = Math.max(0, Math.floor(elapsedMs / 1000));
  const minutes = Math.floor(elapsedSeconds / 60);
  const seconds = elapsedSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function AssistantRunStatus({
  startedAt,
  phase,
  seniorMode,
}: {
  startedAt: number;
  phase: string;
  seniorMode: boolean;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

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
      <span className="ml-auto shrink-0 whitespace-nowrap tabular-nums text-muted-foreground">
        已执行 {formatElapsedTime(now - startedAt)}
      </span>
    </div>
  );
}
