"use client";

import { useDeferredValue, useCallback, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { cn } from "@/lib/utils";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";
import { Button } from "@/components/ui/button";

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
  const [isEditing, setIsEditing] = useState(false);

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
    <div className={cn("flex flex-col h-full w-full", className)}>
      <div className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0 bg-muted/30">
        <div className="flex items-center gap-2">
          <Button
            variant={!isEditing ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setIsEditing(false)}
            disabled={readOnly}
            className="h-7 px-3 text-xs"
          >
            预览
          </Button>
          <Button
            variant={isEditing ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setIsEditing(true)}
            disabled={readOnly}
            className="h-7 px-3 text-xs"
          >
            编辑
          </Button>
        </div>
      </div>

      <div className="flex-1 min-h-0 flex flex-col">
        {isEditing && !readOnly ? (
          <textarea
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            className={cn(
              "flex-1 min-h-0 w-full resize-none bg-transparent p-4 font-mono text-sm leading-relaxed text-foreground outline-none",
              "placeholder:text-muted-foreground"
            )}
            placeholder="开始输入 Markdown..."
            spellCheck={false}
            autoFocus
          />
        ) : (
          <div id="panel-export-content" className="flex-1 min-h-0 overflow-y-auto p-4 bg-white">
            <MarkdownRenderer content={deferredValue} />
          </div>
        )}
      </div>
    </div>
  );
}
