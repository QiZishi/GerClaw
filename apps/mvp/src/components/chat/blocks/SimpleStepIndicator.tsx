"use client";

import { Brain, MessageSquare, Search, Loader2, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SimpleStepData, SimpleStepIcon, SimpleStepStatus } from "@/types";

export type { SimpleStepData, SimpleStepIcon, SimpleStepStatus };

interface SimpleStepIndicatorProps {
  steps: SimpleStepData[];
  className?: string;
}

function StepIcon({ icon, status }: { icon: SimpleStepIcon; status: SimpleStepStatus }) {
  const IconComponent = icon === "thinking" ? Brain : icon === "search" ? Search : MessageSquare;

  if (status === "running") {
    return <Loader2 className="size-3.5 animate-spin" />;
  }
  if (status === "done") {
    return <Check className="size-3.5" />;
  }
  return <IconComponent className="size-3.5" />;
}

export function SimpleStepIndicator({ steps, className }: SimpleStepIndicatorProps) {
  if (!steps || steps.length === 0) return null;

  return (
    <div className={cn("flex items-center gap-1 px-1 py-1 mb-2", className)}>
      {steps.map((step, idx) => {
        const isLast = idx === steps.length - 1;
        return (
          <div key={step.id} className="flex items-center gap-1">
            <div
              className={cn(
                "inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium transition-colors",
                step.status === "running" && "bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-400",
                step.status === "done" && "bg-green-100 text-green-700 dark:bg-green-950/50 dark:text-green-400",
                step.status === "pending" && "bg-muted text-muted-foreground/60"
              )}
            >
              <StepIcon icon={step.icon} status={step.status} />
              <span>{step.label}</span>
            </div>
            {!isLast && (
              <div
                className={cn(
                  "w-4 h-px",
                  step.status === "done" ? "bg-green-400 dark:bg-green-600" : "bg-border"
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
