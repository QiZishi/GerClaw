import { buildMarkdownDocument, buildConversationMarkdown, type ExportConfig } from "./template";
import { downloadBlob, sanitizeFilename } from "./utils";

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
