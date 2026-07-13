"use client";

import { useDeferredValue, useCallback, type ChangeEvent, type KeyboardEvent } from "react";
import { cn } from "@/lib/utils";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";

interface MarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  className?: string;
  readOnly?: boolean;
}

export function MarkdownEditor({
  value,
  onChange,
  className,
  readOnly = false,
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
    <div className={cn("flex flex-col md:flex-row h-full w-full", className)}>
      <div className="flex flex-col flex-1 min-h-0 md:min-w-0 border-b md:border-b-0 md:border-r border-border bg-muted/20">
        <div className="px-3 py-2 text-xs font-medium text-muted-foreground border-b border-border shrink-0 bg-muted/30">
          Markdown
        </div>
        <textarea
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          readOnly={readOnly}
          className={cn(
            "flex-1 min-h-0 w-full resize-none bg-transparent p-4 font-mono text-sm leading-relaxed text-foreground outline-none",
            "placeholder:text-muted-foreground",
            readOnly && "cursor-default opacity-80"
          )}
          placeholder="开始输入 Markdown..."
          spellCheck={false}
        />
      </div>

      <div className="flex flex-col flex-1 min-h-0 md:min-w-0 bg-white">
        <div className="px-3 py-2 text-xs font-medium text-muted-foreground border-b border-border shrink-0 bg-muted/10">
          预览
        </div>
        <div id="panel-export-content" className="flex-1 min-h-0 overflow-y-auto p-4 bg-white">
          <MarkdownRenderer content={deferredValue} />
        </div>
      </div>
    </div>
  );
}
