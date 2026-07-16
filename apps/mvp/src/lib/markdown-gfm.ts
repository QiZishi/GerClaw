/**
 * Chinese clinical text commonly uses a single tilde for numeric ranges
 * (for example, `2~3次`).  GFM's optional single-tilde delete syntax turns
 * that notation into a misleading strikethrough, so only explicit `~~` is
 * treated as deletion throughout the product.
 */
export const MARKDOWN_GFM_OPTIONS = {
  singleTilde: false,
} as const;

/**
 * Some providers occasionally concatenate Markdown blocks while streaming
 * (for example, `---### 标题` or `说明。6. **下一项**`).  Presentation-only
 * normalization restores their block boundaries without changing the stored
 * clinical text or imposing an output format on the agent.
 */
export function normalizeChatMarkdown(content: string): string {
  return content
    .replace(/([^\n])---(?=\s*#{1,6}\s)/g, "$1\n\n---\n\n")
    .replace(/---\s*(?=#{1,6}\s)/g, "---\n\n")
    .replace(/([^\n\d])(?=(?:\d{1,2})\.\s+\*\*)/g, "$1\n")
    .replace(/([^\n#])(?=#{1,6}\s)/g, "$1\n\n");
}
