"use client";

import { CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface InfoField {
  key: string;
  label: string;
  value?: string | number;
  filled: boolean;
}

interface InfoCollectionCardProps {
  fields: InfoField[];
  compact?: boolean;
}

export function InfoCollectionCard({ fields, compact = false }: InfoCollectionCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border/50 bg-card",
        compact ? "p-2" : "p-3"
      )}
    >
      <h4
        className={cn(
          "font-medium text-foreground mb-2",
          compact ? "text-sm" : "text-base"
        )}
      >
        已收集信息
      </h4>
      <div
        className={cn(
          "grid gap-2",
          "grid-cols-2 sm:grid-cols-3 md:grid-cols-4"
        )}
      >
        {fields.map((field) => (
          <div
            key={field.key}
            className={cn(
              "flex items-start gap-1.5",
              compact ? "text-sm" : "text-base"
            )}
          >
            {field.filled ? (
              <CheckCircle2
                className={cn(
                  "text-green-500 shrink-0 mt-0.5",
                  compact ? "size-4" : "size-5"
                )}
              />
            ) : (
              <div
                className={cn(
                  "rounded-full bg-muted shrink-0 mt-0.5",
                  compact ? "size-4" : "size-5"
                )}
              />
            )}
            <div className="min-w-0">
              <span
                className={cn(
                  "text-muted-foreground",
                  compact ? "text-xs" : "text-sm"
                )}
              >
                {field.label}
              </span>
              <p
                className={cn(
                  "font-medium truncate",
                  field.filled ? "text-foreground" : "text-muted-foreground",
                  compact ? "text-sm" : "text-base"
                )}
              >
                {field.filled && field.value !== undefined
                  ? String(field.value)
                  : "待补充"}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
