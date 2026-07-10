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

/**
 * 渲染行内元素，支持嵌套（加粗内可以包含引用、链接等）
 * 匹配优先级：行内代码 > 链接 > 加粗 > 引用角标 > 普通文本
 * 使用分段递归处理，避免误判
 */
function renderInline(text: string, citations?: Citation[]): ReactNode[] {
  return renderInlineSegment(text, citations, 0);
}

type InlineToken =
  | { type: "text"; content: string }
  | { type: "code"; content: string }
  | { type: "bold"; content: string }
  | { type: "link"; text: string; url: string }
  | { type: "citation"; id: number };

function tokenizeInline(text: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  let i = 0;

  while (i < text.length) {
    // 行内代码 `code`
    if (text[i] === "`") {
      const end = text.indexOf("`", i + 1);
      if (end !== -1) {
        tokens.push({ type: "code", content: text.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }

    // Markdown链接 [text](url) — 最高优先级（在引用角标之前）
    if (text[i] === "[") {
      const bracketEnd = text.indexOf("]", i + 1);
      if (bracketEnd !== -1 && text[bracketEnd + 1] === "(") {
        const parenEnd = text.indexOf(")", bracketEnd + 2);
        if (parenEnd !== -1) {
          const linkText = text.slice(i + 1, bracketEnd);
          const linkUrl = text.slice(bracketEnd + 2, parenEnd);
          // 只有当链接文本不是纯数字时才当作链接（纯数字+括号可能是角标被误判，但角标后不会跟括号）
          // 实际上链接的括号模式 [x](y) 本身就足以区分于引用 [n]
          tokens.push({ type: "link", text: linkText, url: linkUrl });
          i = parenEnd + 1;
          continue;
        }
      }
    }

    // 加粗 **text**
    if (text[i] === "*" && text[i + 1] === "*") {
      const end = text.indexOf("**", i + 2);
      if (end !== -1) {
        tokens.push({ type: "bold", content: text.slice(i + 2, end) });
        i = end + 2;
        continue;
      }
    }

    // 引用角标 [n] — 纯数字，且后面不是(（已被链接匹配排除）
    if (text[i] === "[") {
      const bracketEnd = text.indexOf("]", i + 1);
      if (bracketEnd !== -1) {
        const numStr = text.slice(i + 1, bracketEnd);
        if (/^\d+$/.test(numStr)) {
          tokens.push({ type: "citation", id: parseInt(numStr, 10) });
          i = bracketEnd + 1;
          continue;
        }
      }
    }

    // 普通文本：积累到下一个特殊字符
    let textEnd = i + 1;
    while (textEnd < text.length) {
      const ch = text[textEnd];
      if (ch === "`" || ch === "[" || (ch === "*" && text[textEnd + 1] === "*")) {
        break;
      }
      textEnd++;
    }
    const plainContent = text.slice(i, textEnd);
    if (plainContent) {
      tokens.push({ type: "text", content: plainContent });
    }
    i = textEnd;
  }

  return tokens;
}

function renderInlineSegment(text: string, citations: Citation[] | undefined, keyBase: number): ReactNode[] {
  const tokens = tokenizeInline(text);
  return tokens.map((token, idx) => {
    const key = `${keyBase}-${idx}`;
    switch (token.type) {
      case "text":
        return <Fragment key={key}>{token.content}</Fragment>;
      case "code":
        return (
          <code
            key={key}
            className="rounded bg-muted px-1 py-0.5 text-[0.85em] font-mono"
          >
            {token.content}
          </code>
        );
      case "bold":
        return (
          <strong key={key} className="font-semibold">
            {renderInlineSegment(token.content, citations, keyBase * 100 + idx)}
          </strong>
        );
      case "link":
        return (
          <a
            key={key}
            href={token.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            {renderInlineSegment(token.text, citations, keyBase * 100 + idx)}
          </a>
        );
      case "citation": {
        const citeId = token.id;
        const citation = citations?.find((c) => c && c.id === citeId);
        if (citation) {
          return (
            <CitationPopover
              key={key}
              citation={citation}
              index={citeId}
              allCitations={citations}
            />
          );
        }
        return (
          <sup
            key={key}
            className="text-blue-600 dark:text-blue-400 font-semibold text-[0.7em] ml-0.5"
          >
            [{citeId}]
          </sup>
        );
      }
    }
  });
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
