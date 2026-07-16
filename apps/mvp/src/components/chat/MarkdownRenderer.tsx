"use client";

import React, { useState, useEffect, useMemo, Fragment, type ReactNode, type ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { createHighlighter, type Highlighter } from "shiki";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";
import { CitationPopover } from "@/components/search/CitationPopover";
import { useAppStore } from "@/stores/appStore";
import type { Citation } from "@/types";
import { MARKDOWN_GFM_OPTIONS, normalizeChatMarkdown } from "@/lib/markdown-gfm";

interface MarkdownRendererProps {
  content: string;
  citations?: Citation[];
  className?: string;
  style?: React.CSSProperties;
}

let highlighterPromise: Promise<Highlighter> | null = null;

async function getSingletonHighlighter(): Promise<Highlighter> {
  if (!highlighterPromise) {
    highlighterPromise = createHighlighter({
      themes: ["github-light", "github-dark"],
      langs: [
        "javascript",
        "typescript",
        "python",
        "bash",
        "html",
        "css",
        "json",
        "jsx",
        "tsx",
        "markdown",
        "yaml",
        "sql",
        "java",
        "go",
        "rust",
        "php",
        "ruby",
        "c",
        "cpp",
        "csharp",
        "swift",
        "kotlin",
        "plaintext",
      ],
    });
  }
  return highlighterPromise;
}

const SUPPORTED_LANGS = new Set([
  "javascript",
  "typescript",
  "python",
  "bash",
  "html",
  "css",
  "json",
  "jsx",
  "tsx",
  "markdown",
  "yaml",
  "sql",
  "java",
  "go",
  "rust",
  "php",
  "ruby",
  "c",
  "cpp",
  "csharp",
  "swift",
  "kotlin",
  "shell",
  "sh",
  "plaintext",
  "txt",
  "",
]);

function normalizeLang(lang: string | undefined): string {
  if (!lang) return "plaintext";
  const lower = lang.toLowerCase();
  if (lower === "shell" || lower === "sh") return "bash";
  if (lower === "txt") return "plaintext";
  if (SUPPORTED_LANGS.has(lower)) return lower;
  return "plaintext";
}

function useIsDark() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const checkDark = () => {
      if (typeof document !== "undefined") {
        setIsDark(document.documentElement.classList.contains("dark"));
      }
    };

    checkDark();

    const observer = new MutationObserver(checkDark);
    if (typeof document !== "undefined") {
      observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["class"],
      });
    }

    return () => observer.disconnect();
  }, []);

  return isDark;
}

function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const [highlightedHtml, setHighlightedHtml] = useState<string | null>(null);
  const [highlightedCodeKey, setHighlightedCodeKey] = useState("");
  const seniorMode = useAppStore((s) => s.seniorMode);
  const isDark = useIsDark();

  const normalizedLang = normalizeLang(lang);
  const codeKey = `${normalizedLang}:${isDark}:${code}`;

  useEffect(() => {
    let cancelled = false;

    getSingletonHighlighter().then((highlighter) => {
      if (cancelled) return;
      const theme = isDark ? "github-dark" : "github-light";
      const html = highlighter.codeToHtml(code, {
        lang: normalizedLang,
        theme,
      });
      if (!cancelled) {
        setHighlightedHtml(html);
        setHighlightedCodeKey(codeKey);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [code, normalizedLang, isDark, codeKey]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
    }
  };

  const displayLang = lang || "code";

  return (
    <div className="relative group rounded-lg border border-border bg-[#f6f8fa] dark:bg-[#0d1117] overflow-hidden my-3">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-muted/50 dark:bg-muted/20">
        <span className={cn(
          "text-muted-foreground font-mono select-none",
          seniorMode ? "text-lg" : "text-xs"
        )}>
          {displayLang}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className={cn(
            "inline-flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors rounded",
            seniorMode ? "min-h-12 min-w-12 px-3 text-lg" : "text-xs px-1.5 py-1"
          )}
          aria-label="复制代码"
        >
          {copied ? (
            <>
              <Check className={seniorMode ? "size-4" : "size-3.5"} />
              {seniorMode ? "已复制" : null}
            </>
          ) : (
            <>
              <Copy className={seniorMode ? "size-4" : "size-3.5"} />
              {seniorMode ? "复制" : null}
            </>
          )}
        </button>
      </div>
      <div className="overflow-x-auto">
        {highlightedHtml && highlightedCodeKey === codeKey ? (
          <div
            className={cn(
              "shiki-wrapper [&>pre]:!bg-transparent [&>pre]:!m-0 [&>pre]:p-4 [&>pre]:overflow-x-auto",
              seniorMode ? "[&_code]:text-lg [&>pre]:text-lg" : "[&_code]:text-sm [&>pre]:text-sm",
              "[&_code]:leading-relaxed"
            )}
            dangerouslySetInnerHTML={{ __html: highlightedHtml }}
          />
        ) : (
          <pre className={cn(
            "p-4 font-mono overflow-x-auto text-foreground",
            seniorMode ? "text-lg" : "text-sm"
          )}>
            <code>{code}</code>
          </pre>
        )}
      </div>
    </div>
  );
}

function findCitationMatches(text: string): Array<{ fullMatch: string; citeId: number; index: number }> {
  const regex = /\[(\d+)\]/g;
  const matches: Array<{ fullMatch: string; citeId: number; index: number }> = [];
  let match;
  while ((match = regex.exec(text)) !== null) {
    matches.push({
      fullMatch: match[0],
      citeId: parseInt(match[1], 10),
      index: match.index,
    });
  }
  return matches;
}

interface TextWithCitationsProps {
  text: string;
  citations?: Citation[];
}

function TextWithCitations({ text, citations }: TextWithCitationsProps): ReactNode {
  if (!citations || citations.length === 0) {
    return <>{text}</>;
  }

  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;

  const matches = findCitationMatches(text);

  for (const match of matches) {
    const { fullMatch, citeId, index: startIndex } = match;

    if (startIndex > lastIndex) {
      parts.push(<Fragment key={`t-${key++}`}>{text.slice(lastIndex, startIndex)}</Fragment>);
    }

    const citation = citations.find((c) => c && c.id === citeId);
    if (citation) {
      parts.push(
        <CitationPopover
          key={`c-${key++}`}
          citation={citation}
          index={citeId}
          allCitations={citations}
        />
      );
    } else {
      parts.push(
        <sup
          key={`s-${key++}`}
          className="text-blue-600 dark:text-blue-400 font-semibold text-[0.7em] ml-0.5"
        >
          [{citeId}]
        </sup>
      );
    }

    lastIndex = startIndex + fullMatch.length;
  }

  if (lastIndex < text.length) {
    parts.push(<Fragment key={`t-${key++}`}>{text.slice(lastIndex)}</Fragment>);
  }

  return <>{parts}</>;
}

function processChildrenWithCitations(children: ReactNode, citations?: Citation[]): ReactNode {
  if (typeof children === "string") {
    return <TextWithCitations text={children} citations={citations} />;
  }
  if (typeof children === "number" || typeof children === "boolean") {
    return children;
  }
  if (Array.isArray(children)) {
    return children.map((child, idx) => (
      <Fragment key={idx}>{processChildrenWithCitations(child, citations)}</Fragment>
    ));
  }
  if (children && typeof children === "object" && "props" in children) {
    const element = children as React.ReactElement<{ children?: ReactNode }>;
    return React.cloneElement(element, {
      ...element.props,
      children: processChildrenWithCitations(element.props.children, citations),
    });
  }
  return children;
}

type MarkdownComponentProps = ComponentPropsWithoutRef<"div"> & {
  citations?: Citation[];
  seniorMode?: boolean;
  node?: unknown;
};

function createMarkdownComponents(citations?: Citation[], seniorMode?: boolean) {
  return {
    h1: (props: MarkdownComponentProps) => (
      <h1
        className={cn(
          "font-bold mt-5 mb-3 text-foreground",
          seniorMode ? "text-2xl" : "text-xl"
        )}
      >
        {processChildrenWithCitations(props.children, citations)}
      </h1>
    ),
    h2: (props: MarkdownComponentProps) => (
      <h2
        className={cn(
          "font-bold mt-4 mb-2 text-foreground",
          seniorMode ? "text-xl" : "text-lg"
        )}
      >
        {processChildrenWithCitations(props.children, citations)}
      </h2>
    ),
    h3: (props: MarkdownComponentProps) => (
      <h3
        className={cn(
          "font-semibold mt-3 mb-2 text-foreground",
          seniorMode ? "text-lg" : "text-base"
        )}
      >
        {processChildrenWithCitations(props.children, citations)}
      </h3>
    ),
    h4: (props: MarkdownComponentProps) => (
      <h4
        className={cn(
          "font-semibold mt-2 mb-1.5 text-foreground",
          seniorMode ? "text-lg" : "text-sm"
        )}
      >
        {processChildrenWithCitations(props.children, citations)}
      </h4>
    ),
    h5: (props: MarkdownComponentProps) => (
      <h5 className={cn("font-semibold mt-2 mb-1 text-foreground", seniorMode ? "text-lg" : "text-sm")}>
        {processChildrenWithCitations(props.children, citations)}
      </h5>
    ),
    h6: (props: MarkdownComponentProps) => (
      <h6 className={cn("font-semibold mt-2 mb-1 text-muted-foreground uppercase tracking-wide", seniorMode ? "text-lg" : "text-xs")}>
        {processChildrenWithCitations(props.children, citations)}
      </h6>
    ),
    p: (props: MarkdownComponentProps) => (
      <p
        className={cn(
          "mb-3 leading-relaxed text-foreground last:mb-0",
          seniorMode ? "text-lg leading-[1.8]" : "text-sm"
        )}
      >
        {processChildrenWithCitations(props.children, citations)}
      </p>
    ),
    a: (props: MarkdownComponentProps & { href?: string }) => (
      <a
        href={props.href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary hover:underline transition-colors"
      >
        {processChildrenWithCitations(props.children, citations)}
      </a>
    ),
    strong: (props: MarkdownComponentProps) => (
      <strong className="font-semibold text-foreground">
        {processChildrenWithCitations(props.children, citations)}
      </strong>
    ),
    em: (props: MarkdownComponentProps) => (
      <em className="italic">
        {processChildrenWithCitations(props.children, citations)}
      </em>
    ),
    del: (props: MarkdownComponentProps) => (
      <del className="line-through text-muted-foreground">
        {processChildrenWithCitations(props.children, citations)}
      </del>
    ),
    code: ({ inline, className: codeClassName, children, ...props }: MarkdownComponentProps & { inline?: boolean }) => {
      const match = /language-(\w+)/.exec(codeClassName || "");
      const codeString = String(children).replace(/\n$/, "");

      if (!inline && match) {
        return <CodeBlock lang={match[1]} code={codeString} />;
      }

      return (
        <code
          className={cn(
            "rounded bg-muted px-1.5 py-0.5 font-mono text-foreground border border-border/50",
            seniorMode ? "text-lg" : "text-[0.85em]"
          )}
          {...props}
        >
          {children}
        </code>
      );
    },
    pre: ({ children }: MarkdownComponentProps) => (
      <>{children}</>
    ),
    blockquote: (props: MarkdownComponentProps) => {
      const childrenText = String(props.children || "");
      const isSuicideWarning = childrenText.includes("自杀/自伤风险预警") || childrenText.includes("自杀风险预警");
      return (
        <blockquote
          className={cn(
            "border-l-4 pl-4 py-3 my-4 rounded-r-lg",
            isSuicideWarning
              ? "border-red-600 bg-red-600 text-white font-medium"
              : "border-primary/50 bg-muted/40 text-muted-foreground",
            seniorMode ? "text-lg" : "text-sm"
          )}
        >
          {processChildrenWithCitations(props.children, citations)}
        </blockquote>
      );
    },
    ul: (props: MarkdownComponentProps) => (
      <ul
        className={cn(
          "list-disc pl-6 my-3 space-y-1.5",
          seniorMode ? "text-lg" : "text-sm"
        )}
      >
        {processChildrenWithCitations(props.children, citations)}
      </ul>
    ),
    ol: (props: MarkdownComponentProps) => (
      <ol
        className={cn(
          "list-decimal pl-6 my-3 space-y-1.5",
          seniorMode ? "text-lg" : "text-sm"
        )}
      >
        {processChildrenWithCitations(props.children, citations)}
      </ol>
    ),
    li: (props: MarkdownComponentProps) => (
      <li className="leading-relaxed pl-1">
        {processChildrenWithCitations(props.children, citations)}
      </li>
    ),
    table: (props: MarkdownComponentProps) => (
      <div className="overflow-x-auto my-4 rounded-lg border border-border">
        <table className={cn("w-full border-collapse", seniorMode ? "text-lg" : "text-sm")}>
          {processChildrenWithCitations(props.children, citations)}
        </table>
      </div>
    ),
    thead: (props: MarkdownComponentProps) => (
      <thead className="bg-muted/70 dark:bg-muted/30">
        {props.children}
      </thead>
    ),
    tbody: (props: MarkdownComponentProps) => (
      <tbody className="divide-y divide-border">
        {props.children}
      </tbody>
    ),
    tr: (props: MarkdownComponentProps) => (
      <tr className="transition-colors hover:bg-muted/30 even:bg-muted/20">
        {props.children}
      </tr>
    ),
    th: (props: MarkdownComponentProps) => (
      <th
        className={cn(
          "border-b border-border px-4 py-2.5 text-left font-semibold text-foreground",
          seniorMode ? "text-lg" : "text-sm"
        )}
      >
        {processChildrenWithCitations(props.children, citations)}
      </th>
    ),
    td: (props: MarkdownComponentProps) => (
      <td
        className={cn(
          "px-4 py-2.5 text-foreground align-top",
          seniorMode ? "text-lg" : "text-sm"
        )}
      >
        {processChildrenWithCitations(props.children, citations)}
      </td>
    ),
    hr: () => (
      <hr className="my-6 border-t border-border" />
    ),
    img: (props: MarkdownComponentProps & { src?: string; alt?: string }) => (
      // eslint-disable-next-line @next/next/no-img-element -- markdown images are arbitrary external URLs
      <img
        src={props.src}
        alt={props.alt || ""}
        className="max-w-full rounded-lg border border-border my-3"
        loading="lazy"
      />
    ),
  };
}

export function MarkdownRenderer({
  content,
  citations,
  className,
  style,
}: MarkdownRendererProps) {
  const seniorMode = useAppStore((s) => s.seniorMode);
  const presentationContent = useMemo(() => normalizeChatMarkdown(content), [content]);

  const components = useMemo(
    () => createMarkdownComponents(citations, seniorMode),
    [citations, seniorMode]
  );

  return (
    <div
      className={cn(
        "markdown-body",
        seniorMode ? "text-lg leading-[1.8]" : "text-sm leading-relaxed",
        className
      )}
      style={style}
    >
      <ReactMarkdown
        remarkPlugins={[[remarkGfm, MARKDOWN_GFM_OPTIONS]]}
        components={components as Record<string, unknown>}
      >
        {presentationContent}
      </ReactMarkdown>
    </div>
  );
}
