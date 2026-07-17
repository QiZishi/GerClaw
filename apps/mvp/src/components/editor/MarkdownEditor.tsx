"use client";

import { useDeferredValue, useCallback, type ChangeEvent, type KeyboardEvent } from "react";
import { cn } from "@/lib/utils";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";

interface MarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  className?: string;
  readOnly?: boolean;
  seniorMode?: boolean;
}

export function MarkdownEditor({
  value,
  onChange,
  className,
  readOnly = false,
  seniorMode = false,
}: MarkdownEditorProps) {
  const deferredValue = useDeferredValue(value);

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLTextAreaElement>) => {
      onChange(e.target.value);
    },
    [onChange]
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Tab" && !readOnly) {
        e.preventDefault();
        const target = e.currentTarget;
        const start = target.selectionStart;
        const end = target.selectionEnd;
        const newValue = value.substring(0, start) + "  " + value.substring(end);
        onChange(newValue);
        requestAnimationFrame(() => {
          target.selectionStart = target.selectionEnd = start + 2;
        });
      }
    },
    [value, onChange, readOnly]
  );

  return (
    <div className={cn("flex h-full w-full min-h-0 flex-col overflow-y-auto", className)}>
      {!readOnly && (
        <section className="shrink-0 border-b border-border" aria-label="Markdown 编辑区">
          <div className={cn("flex items-center justify-between gap-3 bg-muted/20 px-4 py-2 text-xs text-muted-foreground", seniorMode && "px-5 py-3 text-lg")}>
            <span className="font-medium text-foreground">编辑内容</span>
            <span aria-live="polite">下方实时渲染</span>
          </div>
          <textarea
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            readOnly={readOnly}
            className={cn(
              "block min-h-48 w-full resize-y border-0 bg-transparent p-4 font-mono text-sm leading-relaxed text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/50",
              seniorMode && "min-h-64 p-5 text-lg leading-8"
            )}
            placeholder="开始输入 Markdown..."
            spellCheck={false}
            autoFocus
          />
        </section>
      )}

      <section id="panel-export-content" className="min-h-0 flex-1 bg-white p-4 dark:bg-background" aria-label="实时渲染结果">
        {!readOnly && (
          <p className={cn("mb-3 text-xs text-muted-foreground", seniorMode && "mb-4 text-lg")}>
            实时渲染结果
          </p>
        )}
        <MarkdownRenderer content={deferredValue} />
      </section>
    </div>
  );
}
