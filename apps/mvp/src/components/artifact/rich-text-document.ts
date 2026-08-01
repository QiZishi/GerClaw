const RICH_DOCUMENT_PREFIX = "<!-- gerclaw-rich-document -->";

const BLOCK_TAGS = new Set(["P", "DIV", "H1", "H2", "H3", "H4", "H5", "H6", "LI", "BLOCKQUOTE"]);
const ALLOWED_TAGS = new Set([
  "P",
  "BR",
  "H1",
  "H2",
  "H3",
  "H4",
  "H5",
  "H6",
  "UL",
  "OL",
  "LI",
  "STRONG",
  "B",
  "EM",
  "I",
  "U",
  "SPAN",
  "FONT",
  "A",
  "BLOCKQUOTE",
]);

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function inlineMarkdownToHtml(value: string): string {
  return escapeHtml(value)
    .replace(/!?(\[[^\]]+\])\((https?:\/\/[^\s)]+)\)/g, (_match, label, href) => {
      const text = label.slice(1, -1);
      return `<a href="${escapeHtml(href)}" target="_blank" rel="noreferrer">${text}</a>`;
    })
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<span style=\"font-family: ui-monospace, SFMono-Regular, Menlo, monospace\">$1</span>");
}

/**
 * Converts legacy Markdown into an editable, browser-safe document surface.
 * New rich documents are deliberately persisted as an HTML block in the existing
 * `markdown` field, so the Artifact API contract remains backward compatible.
 */
export function artifactMarkdownToRichHtml(markdown: string): string {
  const trimmed = markdown.trim();
  if (trimmed.startsWith(RICH_DOCUMENT_PREFIX)) {
    return trimmed.slice(RICH_DOCUMENT_PREFIX.length).trim() || "<p><br></p>";
  }

  const output: string[] = [];
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  let listType: "ul" | "ol" | null = null;
  const closeList = () => {
    if (listType) output.push(`</${listType}>`);
    listType = null;
  };

  for (const line of lines) {
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (heading) {
      closeList();
      const level = Math.min(6, heading[1].length);
      output.push(`<h${level}>${inlineMarkdownToHtml(heading[2])}</h${level}>`);
    } else if (unordered || ordered) {
      const nextType = unordered ? "ul" : "ol";
      if (listType !== nextType) {
        closeList();
        listType = nextType;
        output.push(`<${listType}>`);
      }
      output.push(`<li>${inlineMarkdownToHtml((unordered ?? ordered)![1])}</li>`);
    } else if (line.trim().startsWith("> ")) {
      closeList();
      output.push(`<blockquote><p>${inlineMarkdownToHtml(line.trim().slice(2))}</p></blockquote>`);
    } else if (!line.trim()) {
      closeList();
    } else {
      closeList();
      output.push(`<p>${inlineMarkdownToHtml(line)}</p>`);
    }
  }
  closeList();
  return output.join("") || "<p><br></p>";
}

function allowedHref(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.origin);
    return ["http:", "https:", "mailto:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function sanitizedNode(node: Node, document: Document): Node | null {
  if (node.nodeType === Node.TEXT_NODE) return document.createTextNode(node.textContent ?? "");
  if (node.nodeType !== Node.ELEMENT_NODE) return null;
  const element = node as HTMLElement;
  const tagName = element.tagName.toUpperCase();
  if (!ALLOWED_TAGS.has(tagName)) {
    const fragment = document.createDocumentFragment();
    for (const child of Array.from(element.childNodes)) {
      const cleanChild = sanitizedNode(child, document);
      if (cleanChild) fragment.append(cleanChild);
    }
    return fragment;
  }

  const clean = document.createElement(tagName.toLowerCase());
  if (tagName === "FONT") {
    const fontSize = element.getAttribute("size");
    const sizeMap: Record<string, string> = { "2": "14px", "3": "16px", "4": "18px", "5": "22px" };
    const span = document.createElement("span");
    if (fontSize && sizeMap[fontSize]) span.style.fontSize = sizeMap[fontSize];
    const color = element.getAttribute("color");
    if (color) span.style.color = color;
    for (const child of Array.from(element.childNodes)) {
      const cleanChild = sanitizedNode(child, document);
      if (cleanChild) span.append(cleanChild);
    }
    return span;
  }
  if (tagName === "A") {
    const href = allowedHref(element.getAttribute("href"));
    if (href) {
      clean.setAttribute("href", href);
      clean.setAttribute("target", "_blank");
      clean.setAttribute("rel", "noreferrer");
    }
  }
  if (tagName === "SPAN") {
    const color = element.style.color;
    const size = element.style.fontSize;
    if (color) clean.style.color = color;
    if (/^\d{1,2}px$/.test(size)) clean.style.fontSize = size;
  }
  for (const child of Array.from(element.childNodes)) {
    const cleanChild = sanitizedNode(child, document);
    if (cleanChild) clean.append(cleanChild);
  }
  return clean;
}

export function sanitizeRichHtml(html: string): string {
  if (typeof window === "undefined") {
    return html
      .replace(/<(script|style|iframe|object|embed)[^>]*>[\s\S]*?<\/\1>/gi, "")
      .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, "")
      .replace(/\s(?:href|src)\s*=\s*(["'])\s*javascript:[\s\S]*?\1/gi, "");
  }
  const source = new DOMParser().parseFromString(html, "text/html");
  const output = document.createElement("div");
  for (const child of Array.from(source.body.childNodes)) {
    const clean = sanitizedNode(child, document);
    if (clean) output.append(clean);
  }
  for (const child of Array.from(output.childNodes)) {
    if (child.nodeType === Node.TEXT_NODE && child.textContent?.trim()) {
      const paragraph = document.createElement("p");
      paragraph.textContent = child.textContent;
      output.replaceChild(paragraph, child);
    }
  }
  return output.innerHTML || "<p><br></p>";
}

function markdownFromNode(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? "";
  if (node.nodeType !== Node.ELEMENT_NODE) return "";
  const element = node as HTMLElement;
  const content = Array.from(element.childNodes).map(markdownFromNode).join("");
  switch (element.tagName) {
    case "H1": return `# ${content.trim()}\n\n`;
    case "H2": return `## ${content.trim()}\n\n`;
    case "H3": return `### ${content.trim()}\n\n`;
    case "H4": return `#### ${content.trim()}\n\n`;
    case "H5": return `##### ${content.trim()}\n\n`;
    case "H6": return `###### ${content.trim()}\n\n`;
    case "P": return `${content.trim()}\n\n`;
    case "BR": return "\n";
    case "STRONG":
    case "B": return `**${content}**`;
    case "EM":
    case "I": return `*${content}*`;
    case "U": return `<u>${content}</u>`;
    case "SPAN": {
      const styles = [element.style.color && `color:${element.style.color}`, element.style.fontSize && `font-size:${element.style.fontSize}`]
        .filter(Boolean)
        .join(";");
      return styles ? `<span style="${styles}">${content}</span>` : content;
    }
    case "A": {
      const href = allowedHref(element.getAttribute("href"));
      return href ? `[${content}](${href})` : content;
    }
    case "LI": return content.trim();
    case "UL": return Array.from(element.children).map((item) => `- ${markdownFromNode(item).trim()}`).join("\n") + "\n\n";
    case "OL": return Array.from(element.children).map((item, index) => `${index + 1}. ${markdownFromNode(item).trim()}`).join("\n") + "\n\n";
    case "BLOCKQUOTE": return content.trim().split("\n").map((line) => `> ${line}`).join("\n") + "\n\n";
    default: return content;
  }
}

export function richHtmlToArtifactMarkdown(html: string): string {
  if (typeof window === "undefined") return html;
  const cleanHtml = sanitizeRichHtml(html);
  const source = new DOMParser().parseFromString(cleanHtml, "text/html");
  const hasRichOnlyFormatting = Boolean(source.body.querySelector("u, span[style]"));
  const markdown = Array.from(source.body.childNodes).map(markdownFromNode).join("").trim();
  return hasRichOnlyFormatting ? `${RICH_DOCUMENT_PREFIX}\n${cleanHtml}` : markdown;
}

export function richHtmlToPlainText(html: string): string {
  if (typeof window === "undefined") {
    return sanitizeRichHtml(html)
      .replace(/<br\s*\/?\s*>/gi, "\n")
      .replace(/<\/(p|div|h[1-6]|li|blockquote)>/gi, "\n")
      .replace(/<[^>]+>/g, "")
      .replace(/&nbsp;/g, " ")
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }
  const document = new DOMParser().parseFromString(sanitizeRichHtml(html), "text/html");
  return Array.from(document.body.childNodes)
    .map((node) => BLOCK_TAGS.has(node.nodeName) ? `${node.textContent ?? ""}\n` : node.textContent ?? "")
    .join("")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
