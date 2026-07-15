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
  seniorMode?: boolean;
  defaultMode?: "preview" | "source";
}

export function MarkdownEditor({
  value,
  onChange,
  className,
  readOnly = false,
  seniorMode = false,
  defaultMode = "preview",
}: MarkdownEditorProps) {
  const deferredValue = useDeferredValue(value);
  const [isEditing, setIsEditing] = useState(defaultMode === "source");

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
    <div className={cn("flex h-full w-full flex-col", className)}>
      <div className="flex shrink-0 items-center justify-between border-b border-border bg-muted/30 px-3 py-2">
        <div className="flex items-center gap-2">
          <Button
            variant={!isEditing ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setIsEditing(false)}
            className={cn("h-8 px-3 text-xs", seniorMode && "h-12 px-4 text-lg")}
          >
            渲染预览
          </Button>
          <Button
            variant={isEditing ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setIsEditing(true)}
            className={cn("h-8 px-3 text-xs", seniorMode && "h-12 px-4 text-lg")}
          >
            SKILL.md 源码
          </Button>
        </div>
        {readOnly && (
          <span className={cn("text-xs font-medium text-muted-foreground", seniorMode && "text-lg")}>
            只读
          </span>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        {isEditing ? (
          <textarea
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            readOnly={readOnly}
            className={cn(
              "min-h-0 w-full flex-1 resize-none bg-transparent p-4 font-mono text-sm leading-relaxed text-foreground outline-none placeholder:text-muted-foreground",
              seniorMode && "text-lg leading-8",
              readOnly && "cursor-text bg-muted/15"
            )}
            placeholder="开始输入 Markdown..."
            spellCheck={false}
            autoFocus={!readOnly}
          />
        ) : (
          <div id="panel-export-content" className="min-h-0 flex-1 overflow-y-auto bg-white p-4 dark:bg-background">
            <MarkdownRenderer content={deferredValue} />
          </div>
        )}
      </div>
    </div>
  );
}
