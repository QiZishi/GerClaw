import { buildMarkdownDocument, buildConversationMarkdown, type ExportConfig } from "./template";
import { downloadBlob, sanitizeFilename } from "./utils";
import {
  artifactMarkdownToRichHtml,
  sanitizeRichHtml,
} from "@/components/artifact/rich-text-document";

export function exportToMarkdown(config: ExportConfig): void {
  const markdown = buildMarkdownDocument(config);
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const filename = `${sanitizeFilename(config.title)}.md`;
  downloadBlob(blob, filename);
}

export function exportConversationToMarkdown(
  title: string,
  messages: { role: "user" | "assistant"; content: string }[]
): void {
  const markdown = buildConversationMarkdown(title, messages);
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const filename = `${sanitizeFilename(title)}.md`;
  downloadBlob(blob, filename);
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function completeHtml(title: string, body: string, subtitle?: string): string {
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${escapeHtml(title)}</title><style>body{max-width:860px;margin:40px auto;padding:0 32px;color:#172033;font:16px/1.8 system-ui,-apple-system,sans-serif}h1{font-size:2rem}h2{font-size:1.5rem;margin-top:2rem}h3{font-size:1.25rem;margin-top:1.5rem}a{color:#175cd3}blockquote{border-left:4px solid #cbd5e1;padding-left:1rem;color:#475569}.document-meta{color:#64748b;border-bottom:1px solid #e2e8f0;padding-bottom:1rem;margin-bottom:2rem}</style></head><body><header><h1>${escapeHtml(title)}</h1>${subtitle ? `<p class="document-meta">${escapeHtml(subtitle)}</p>` : ""}</header>${body}</body></html>`;
}

export function exportToHtml(
  config: ExportConfig,
  renderedHtml?: string,
): void {
  const body = sanitizeRichHtml(renderedHtml ?? artifactMarkdownToRichHtml(config.content));
  downloadBlob(
    new Blob([completeHtml(config.title, body, config.subtitle)], {
      type: "text/html;charset=utf-8",
    }),
    `${sanitizeFilename(config.title)}.html`,
  );
}

export function exportConversationToHtml(
  title: string,
  messages: { role: "user" | "assistant"; content: string }[],
): void {
  const body = messages
    .map(
      (message) =>
        `<section><h2>${message.role === "user" ? "用户" : "GerClaw"}</h2>${sanitizeRichHtml(
          artifactMarkdownToRichHtml(message.content),
        )}</section>`,
    )
    .join("");
  downloadBlob(
    new Blob([completeHtml(title, body, "GerClaw 对话记录")], {
      type: "text/html;charset=utf-8",
    }),
    `${sanitizeFilename(title)}.html`,
  );
}
