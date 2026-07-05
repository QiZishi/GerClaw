"use client";

import { Fragment, useState, type ReactNode } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";
import { CitationPopover } from "@/components/search/CitationPopover";
import type { Citation } from "@/types";

interface MarkdownRendererProps {
  content: string;
  citations?: Citation[];
  className?: string;
}

/**
 * 简单 Markdown 渲染（不依赖外部库）
 * 支持：标题 # ## ###、列表 -/*、代码块 ```、引用 >、加粗 **、链接 []()、引用角标 [1]
 * 不使用 dangerouslySetInnerHTML，通过正则分段+React 元素渲染，防 XSS
 */
export function MarkdownRenderer({
  content,
  citations,
  className,
}: MarkdownRendererProps) {
  const blocks = parseMarkdown(content);

  return (
    <div className={cn("space-y-2 text-sm leading-relaxed", className)}>
      {blocks.map((block, idx) => (
        <BlockRenderer
          key={idx}
          block={block}
          citations={citations}
        />
      ))}
    </div>
  );
}

// === 解析 ===

type MdBlock =
  | { type: "h1" | "h2" | "h3"; text: string }
  | { type: "ul" | "ol"; items: string[] }
  | { type: "code"; lang: string; code: string }
  | { type: "quote"; text: string }
  | { type: "table"; header: string[]; rows: string[][] }
  | { type: "paragraph"; text: string };

function parseMarkdown(src: string): MdBlock[] {
  const lines = src.split("\n");
  const blocks: MdBlock[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    // 代码块
    const codeFenceMatch = line.match(/^```(\w*)/);
    if (codeFenceMatch) {
      const lang = codeFenceMatch[1] ?? "";
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // 跳过结束 ```
      blocks.push({ type: "code", lang, code: codeLines.join("\n") });
      continue;
    }

    // 标题
    const h3 = line.match(/^###\s+(.*)/);
    if (h3) {
      blocks.push({ type: "h3", text: h3[1] });
      i++;
      continue;
    }
    const h2 = line.match(/^##\s+(.*)/);
    if (h2) {
      blocks.push({ type: "h2", text: h2[1] });
      i++;
      continue;
    }
    const h1 = line.match(/^#\s+(.*)/);
    if (h1) {
      blocks.push({ type: "h1", text: h1[1] });
      i++;
      continue;
    }

    // 引用
    const quote = line.match(/^>\s+(.*)/);
    if (quote) {
      const quoteLines: string[] = [quote[1]];
      i++;
      while (i < lines.length && /^>\s+/.test(lines[i])) {
        quoteLines.push(lines[i].replace(/^>\s+/, ""));
        i++;
      }
      blocks.push({ type: "quote", text: quoteLines.join("\n") });
      continue;
    }

    // 表格
    if (/\|/.test(line) && i + 1 < lines.length && /^\|?[\s-:|]+\|/.test(lines[i + 1])) {
      const header = line.split("|").map((s) => s.trim()).filter(Boolean);
      i += 2; // 跳过分隔行
      const rows: string[][] = [];
      while (i < lines.length && /\|/.test(lines[i])) {
        rows.push(lines[i].split("|").map((s) => s.trim()).filter(Boolean));
        i++;
      }
      blocks.push({ type: "table", header, rows });
      continue;
    }

    // 无序列表
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      blocks.push({ type: "ul", items });
      continue;
    }

    // 有序列表
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ""));
        i++;
      }
      blocks.push({ type: "ol", items });
      continue;
    }

    // 空行
    if (line.trim() === "") {
      i++;
      continue;
    }

    // 段落（连续非空非语法行）
    const paraLines: string[] = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^(#{1,3}\s|```|>\s|\s*[-*]\s|\s*\d+\.\s)/.test(lines[i])
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    blocks.push({ type: "paragraph", text: paraLines.join("\n") });
  }
  return blocks;
}

// === 渲染 ===

function BlockRenderer({
  block,
  citations,
}: {
  block: MdBlock;
  citations?: Citation[];
}) {
  switch (block.type) {
    case "h1":
      return (
        <h1 className="text-xl font-bold mt-3 mb-1">
          {renderInline(block.text, citations)}
        </h1>
      );
    case "h2":
      return (
        <h2 className="text-lg font-bold mt-3 mb-1">
          {renderInline(block.text, citations)}
        </h2>
      );
    case "h3":
      return (
        <h3 className="text-base font-semibold mt-2 mb-1">
          {renderInline(block.text, citations)}
        </h3>
      );
    case "ul":
      return (
        <ul className="list-disc pl-5 space-y-1">
          {block.items.map((item, idx) => (
            <li key={idx}>{renderInline(item, citations)}</li>
          ))}
        </ul>
      );
    case "ol":
      return (
        <ol className="list-decimal pl-5 space-y-1">
          {block.items.map((item, idx) => (
            <li key={idx}>{renderInline(item, citations)}</li>
          ))}
        </ol>
      );
    case "code":
      return <CodeBlock lang={block.lang} code={block.code} />;
    case "quote":
      return (
        <blockquote className="border-l-4 border-border pl-3 py-1 text-muted-foreground italic">
          {renderInline(block.text, citations)}
        </blockquote>
      );
    case "table":
      return (
        <div className="overflow-x-auto">
          <table className="min-w-full text-xs border border-border rounded">
            <thead className="bg-muted">
              <tr>
                {block.header.map((h, idx) => (
                  <th key={idx} className="border border-border px-2 py-1 text-left">
                    {renderInline(h, citations)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, ridx) => (
                <tr key={ridx}>
                  {row.map((cell, cidx) => (
                    <td key={cidx} className="border border-border px-2 py-1">
                      {renderInline(cell, citations)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "paragraph":
      return (
        <p className="whitespace-pre-wrap">
          {renderInline(block.text, citations)}
        </p>
      );
  }
}

/** 渲染行内：**加粗** [链接](url) [1]引用角标 */
function renderInline(text: string, citations?: Citation[]): ReactNode[] {
  // 先按 [1] 引用角标分割
  const nodes: ReactNode[] = [];
  const parts = text.split(/(\[\d+\])/g);
  parts.forEach((part, idx) => {
    const citeMatch = part.match(/^\[(\d+)\]$/);
    if (citeMatch) {
      const citeId = parseInt(citeMatch[1], 10);
      // 防御性：citations 数组可能含 undefined 元素
      const citation = citations?.find((c) => c && c.id === citeId);
      if (citation) {
        nodes.push(
          <CitationPopover key={`cite-${idx}`} citation={citation} index={citeId} />
        );
      } else {
        nodes.push(
          <sup key={`cite-${idx}`} className="text-primary font-bold">
            [{citeId}]
          </sup>
        );
      }
      return;
    }
    // 加粗 + 链接
    nodes.push(...renderBoldAndLink(part, idx));
  });
  return nodes;
}

/** 渲染 **加粗** 和 [文本](url) */
function renderBoldAndLink(text: string, baseKey: number): ReactNode[] {
  // 正则：**bold** 或 [text](url)
  const regex = /(\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)]+)\))/g;
  const result: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let keyCounter = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      result.push(
        <Fragment key={`${baseKey}-${keyCounter++}`}>
          {text.slice(lastIndex, match.index)}
        </Fragment>
      );
    }
    if (match[2]) {
      // 加粗
      result.push(
        <strong key={`${baseKey}-${keyCounter++}`} className="font-semibold">
          {match[2]}
        </strong>
      );
    } else if (match[3] && match[4]) {
      // 链接
      result.push(
        <a
          key={`${baseKey}-${keyCounter++}`}
          href={match[4]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary hover:underline"
        >
          {match[3]}
        </a>
      );
    }
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    result.push(
      <Fragment key={`${baseKey}-${keyCounter++}`}>
        {text.slice(lastIndex)}
      </Fragment>
    );
  }
  if (result.length === 0) {
    return [<Fragment key={`${baseKey}-empty`}>{text}</Fragment>];
  }
  return result;
}

/** 代码块 + 复制按钮 */
function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard?.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="relative group rounded-lg border border-border bg-muted/60 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1 border-b border-border/60 bg-muted">
        <span className="text-xs text-muted-foreground font-mono">
          {lang || "code"}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
          aria-label="复制代码"
        >
          {copied ? (
            <>
              <Check className="size-3" />
              已复制
            </>
          ) : (
            <>
              <Copy className="size-3" />
              复制
            </>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-xs leading-relaxed">
        <code className="font-mono">{code}</code>
      </pre>
    </div>
  );
}
