"use client";

import { useCallback, useEffect, useRef } from "react";
import {
  Bold,
  List,
  ListOrdered,
  Redo2,
  Underline,
  Undo2,
} from "lucide-react";

import {
  artifactMarkdownToRichHtml,
  richHtmlToArtifactMarkdown,
  sanitizeRichHtml,
} from "@/components/artifact/rich-text-document";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface RichTextArtifactEditorProps {
  value: string;
  onChange: (value: string) => void;
  className?: string;
  seniorMode?: boolean;
}

function command(commandName: string, value?: string) {
  document.execCommand(commandName, false, value);
}

export function RichTextArtifactEditor({
  value,
  onChange,
  className,
  seniorMode = false,
}: RichTextArtifactEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null);
  const serializedRef = useRef(value);
  const selectionRef = useRef<Range | null>(null);

  useEffect(() => {
    if (!editorRef.current || (editorRef.current.innerHTML && serializedRef.current === value)) return;
    const nextHtml = sanitizeRichHtml(artifactMarkdownToRichHtml(value));
    editorRef.current.innerHTML = nextHtml;
    serializedRef.current = value;
  }, [value]);

  const sync = useCallback(() => {
    const editor = editorRef.current;
    if (!editor) return;
    const next = richHtmlToArtifactMarkdown(editor.innerHTML);
    serializedRef.current = next;
    onChange(next);
  }, [onChange]);

  const rememberSelection = useCallback(() => {
    const editor = editorRef.current;
    const selection = window.getSelection();
    if (!editor || !selection || selection.rangeCount === 0) return;
    const range = selection.getRangeAt(0);
    if (editor.contains(range.commonAncestorContainer)) selectionRef.current = range.cloneRange();
  }, []);

  const apply = useCallback((name: string, commandValue?: string) => {
    const editor = editorRef.current;
    if (!editor) return;
    editor.focus();
    const selection = window.getSelection();
    if (selection && selectionRef.current) {
      selection.removeAllRanges();
      selection.addRange(selectionRef.current);
    }
    command(name, commandValue);
    rememberSelection();
    sync();
  }, [rememberSelection, sync]);

  const createLink = useCallback(() => {
    const href = window.prompt("输入链接地址（https://）");
    if (!href?.trim()) return;
    apply("createLink", href.trim());
  }, [apply]);

  const onPaste = useCallback((event: React.ClipboardEvent<HTMLDivElement>) => {
    event.preventDefault();
    const text = event.clipboardData.getData("text/plain");
    command("insertText", text);
    sync();
  }, [sync]);

  const toolButtonClass = cn(
    "min-w-8 gap-1 px-2 text-xs",
    seniorMode && "min-h-12 min-w-12 text-base",
  );

  return (
    <section className={cn("flex min-h-0 flex-1 flex-col overflow-y-auto bg-[#f4f6f8] p-3 dark:bg-background", className)} aria-label="文档编辑区">
      <div className={cn("sticky top-0 z-10 mx-auto flex w-full max-w-[920px] shrink-0 flex-wrap items-center gap-1 border border-slate-200 bg-white px-2 py-1.5 shadow-sm dark:border-border dark:bg-card", seniorMode && "gap-2 px-3 py-2")} role="toolbar" aria-label="文档格式工具" onMouseDown={rememberSelection}>
        <label className={cn("flex items-center gap-1 text-xs text-muted-foreground", seniorMode && "text-base")}>
          段落
          <select
            className={cn("h-8 rounded border border-border bg-background px-1 text-xs text-foreground", seniorMode && "h-12 text-base")}
            aria-label="标题层级"
            defaultValue="P"
            onChange={(event) => apply("formatBlock", event.target.value)}
          >
            <option value="P">正文</option>
            <option value="H1">标题 1</option>
            <option value="H2">标题 2</option>
            <option value="H3">标题 3</option>
          </select>
        </label>
        <label className={cn("flex items-center gap-1 text-xs text-muted-foreground", seniorMode && "text-base")}>
          字号
          <select
            className={cn("h-8 rounded border border-border bg-background px-1 text-xs text-foreground", seniorMode && "h-12 text-base")}
            aria-label="字体大小"
            defaultValue="3"
            onChange={(event) => apply("fontSize", event.target.value)}
          >
            <option value="2">小</option>
            <option value="3">常规</option>
            <option value="4">大</option>
            <option value="5">特大</option>
          </select>
        </label>
        <Button type="button" variant="ghost" size="sm" className={toolButtonClass} onClick={() => apply("bold")} aria-label="加粗"><Bold className="size-4" />加粗</Button>
        <Button type="button" variant="ghost" size="sm" className={toolButtonClass} onClick={() => apply("underline")} aria-label="下划线"><Underline className="size-4" />下划线</Button>
        <label className={cn("flex min-h-8 items-center gap-1 px-1 text-xs text-muted-foreground", seniorMode && "min-h-12 text-base")}>
          颜色
          <input type="color" aria-label="文字颜色" className="size-6 cursor-pointer rounded border-0 bg-transparent" onChange={(event) => apply("foreColor", event.target.value)} />
        </label>
        <Button type="button" variant="ghost" size="sm" className={toolButtonClass} onClick={() => apply("insertUnorderedList")} aria-label="无序列表"><List className="size-4" />列表</Button>
        <Button type="button" variant="ghost" size="sm" className={toolButtonClass} onClick={() => apply("insertOrderedList")} aria-label="有序列表"><ListOrdered className="size-4" />编号</Button>
        <Button type="button" variant="ghost" size="sm" className={toolButtonClass} onClick={createLink} aria-label="插入链接">链接</Button>
        <span className="mx-1 h-5 w-px bg-border" aria-hidden />
        <Button type="button" variant="ghost" size="sm" className={toolButtonClass} onClick={() => apply("undo")} aria-label="撤销"><Undo2 className="size-4" />撤销</Button>
        <Button type="button" variant="ghost" size="sm" className={toolButtonClass} onClick={() => apply("redo")} aria-label="重做"><Redo2 className="size-4" />重做</Button>
      </div>
      <div className="min-h-3 shrink-0" />
      <article
        id="panel-export-content"
        ref={editorRef}
        contentEditable
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        aria-label="可编辑文档正文"
        tabIndex={0}
        onInput={sync}
        onPaste={onPaste}
        onKeyUp={rememberSelection}
        onMouseUp={rememberSelection}
        className={cn(
          "artifact-document-page mx-auto min-h-[680px] w-full max-w-[920px] shrink-0 bg-white px-10 py-12 text-[16px] leading-8 text-slate-900 shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring dark:bg-card dark:text-foreground",
          "[&_a]:cursor-pointer [&_a]:text-blue-700 [&_a]:underline [&_blockquote]:border-l-4 [&_blockquote]:border-slate-300 [&_blockquote]:pl-4 [&_blockquote]:text-slate-600 [&_h1]:mb-5 [&_h1]:text-3xl [&_h1]:font-bold [&_h1]:leading-tight [&_h2]:mb-4 [&_h2]:mt-8 [&_h2]:text-2xl [&_h2]:font-bold [&_h3]:mb-3 [&_h3]:mt-6 [&_h3]:text-xl [&_h3]:font-semibold [&_ol]:my-4 [&_ol]:list-decimal [&_ol]:pl-7 [&_p]:my-0 [&_p]:min-h-8 [&_ul]:my-4 [&_ul]:list-disc [&_ul]:pl-7",
          seniorMode && "min-h-[760px] px-6 py-8 text-lg leading-9 [&_h1]:text-4xl [&_h2]:text-3xl [&_h3]:text-2xl",
        )}
      />
    </section>
  );
}
