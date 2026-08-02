"use client";
import { useEffect, useState } from "react";
import { Activity, AlertTriangle, Check, Clock, Cpu } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Message } from "@/types";

function formatElapsed(milliseconds: number): string {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

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
  message = "这次回答没有完整生成，请重试",
}: {
  seniorMode: boolean;
  message?: string;
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
        {message}
      </p>
    </section>
  );
}

export function AssistantRunStatus({
  phase,
  seniorMode,
  startedAt,
}: {
  phase: string;
  seniorMode: boolean;
  startedAt: number;
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
      <span className="inline-flex items-center gap-1 text-foreground/70">
        <Clock className="size-3.5" aria-hidden />
        已执行 {formatElapsed(now - startedAt)}
      </span>
    </div>
  );
}

export function AgentExecutionSummary({
  message,
  seniorMode,
}: {
  message: Message;
  seniorMode: boolean;
}) {
  if (!message.modelExecution) return null;
  const elapsed = Math.max(0, (message.completedAt ?? message.createdAt) - message.createdAt);
  const slotLabel = {
    primary: "主模型",
    backup1: "备用模型 1",
    backup2: "备用模型 2",
  }[message.modelExecution?.modelSlot ?? "primary"];

  return (
    <details className="w-full overflow-hidden rounded-xl border border-border/70 bg-muted/20">
      <summary className={cn("flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm text-muted-foreground hover:bg-muted/40", seniorMode && "min-h-12 text-base")}>
        <span className="inline-flex items-center gap-1.5 font-medium text-foreground">
          <Activity className="size-4 text-primary" aria-hidden />
          执行详情
        </span>
        <span className="inline-flex items-center gap-1">
          <Clock className="size-3.5" aria-hidden />
          {formatElapsed(elapsed)}
        </span>
        {message.modelExecution && (
          <span className="truncate">
            {message.modelExecution.provider} · {message.modelExecution.model}
          </span>
        )}
      </summary>
      <div className={cn("space-y-2 border-t border-border/60 px-3 py-3 text-sm", seniorMode && "text-base leading-8")}>
        {message.modelExecution && (
          <div className="flex items-start gap-2">
            <Cpu className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
            <div>
              <div className="font-medium">模型服务</div>
              <div className="break-words text-muted-foreground">
                {message.modelExecution.provider} · {message.modelExecution.model} · {slotLabel}
              </div>
            </div>
          </div>
        )}
        <div className="flex items-start gap-2">
          <Check className="mt-0.5 size-4 shrink-0 text-emerald-700" aria-hidden />
          <div>
            <div className="font-medium">本次执行</div>
            <div className="text-muted-foreground">已完成 · 用时 {formatElapsed(elapsed)}</div>
          </div>
        </div>
      </div>
    </details>
  );
}
