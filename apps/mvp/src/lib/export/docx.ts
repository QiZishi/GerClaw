import {
  Document,
  Packer,
  Paragraph,
  TextRun,
  HeadingLevel,
  ExternalHyperlink,
  UnderlineType,
  type ParagraphChild,
} from "docx";
import { saveAs } from "file-saver";
import { sanitizeFilename } from "./utils";
import { MEDICAL_EXPORT_DISCLAIMER } from "./template";
import {
  artifactMarkdownToRichHtml,
  sanitizeRichHtml,
} from "@/components/artifact/rich-text-document";

interface InlineStyle {
  bold?: boolean;
  italics?: boolean;
  underline?: boolean;
  color?: string;
  size?: number;
}

function docxColor(value: string): string | undefined {
  const hex = /^#([0-9a-f]{6})$/i.exec(value.trim());
  if (hex) return hex[1].toUpperCase();
  const rgb = /^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/i.exec(value.trim());
  if (!rgb) return undefined;
  return rgb
    .slice(1)
    .map((part) => Number(part).toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase();
}

function docxSize(value: string): number | undefined {
  const match = /^(\d+(?:\.\d+)?)px$/.exec(value.trim());
  if (!match) return undefined;
  return Math.max(16, Math.min(72, Math.round(Number(match[1]) * 1.5)));
}

function textRun(text: string, style: InlineStyle): TextRun {
  return new TextRun({
    text,
    bold: style.bold,
    italics: style.italics,
    underline: style.underline ? { type: UnderlineType.SINGLE } : undefined,
    color: style.color,
    size: style.size,
  });
}

function safeExternalHref(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.origin);
    return ["http:", "https:", "mailto:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function inlineChildren(node: Node, inherited: InlineStyle = {}): ParagraphChild[] {
  if (node.nodeType === Node.TEXT_NODE) {
    return node.textContent ? [textRun(node.textContent, inherited)] : [];
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return [];
  const element = node as HTMLElement;
  if (element.tagName === "BR") return [textRun("\n", inherited)];
  const next: InlineStyle = { ...inherited };
  if (["STRONG", "B"].includes(element.tagName)) next.bold = true;
  if (["EM", "I"].includes(element.tagName)) next.italics = true;
  if (element.tagName === "U") next.underline = true;
  const color = docxColor(element.style.color || element.getAttribute("color") || "");
  const size = docxSize(element.style.fontSize || "");
  if (color) next.color = color;
  if (size) next.size = size;
  const children = Array.from(element.childNodes).flatMap((child) => inlineChildren(child, next));
  if (element.tagName !== "A") return children;
  const href = safeExternalHref(element.getAttribute("href"));
  const linkRuns = children.filter((child): child is TextRun => child instanceof TextRun);
  return href && linkRuns.length > 0
    ? [new ExternalHyperlink({ link: href, children: linkRuns })]
    : children;
}

function renderedHtmlToDocxParagraphs(html: string): Paragraph[] {
  const parsed = new DOMParser().parseFromString(sanitizeRichHtml(html), "text/html");
  const paragraphs: Paragraph[] = [];
  const appendBlock = (element: Element, listKind?: "ul" | "ol", index = 0) => {
    if (element.tagName === "UL" || element.tagName === "OL") {
      Array.from(element.children).forEach((child, itemIndex) =>
        appendBlock(child, element.tagName.toLowerCase() as "ul" | "ol", itemIndex),
      );
      return;
    }
    const heading = {
      H1: HeadingLevel.HEADING_1,
      H2: HeadingLevel.HEADING_2,
      H3: HeadingLevel.HEADING_3,
      H4: HeadingLevel.HEADING_4,
      H5: HeadingLevel.HEADING_5,
      H6: HeadingLevel.HEADING_6,
    }[element.tagName];
    const children = Array.from(element.childNodes).flatMap((child) => inlineChildren(child));
    if (listKind === "ol") children.unshift(new TextRun({ text: `${index + 1}. ` }));
    paragraphs.push(
      new Paragraph({
        children,
        heading,
        bullet: listKind === "ul" ? { level: 0 } : undefined,
        indent: element.tagName === "BLOCKQUOTE" ? { left: 480 } : undefined,
      }),
    );
  };
  for (const child of Array.from(parsed.body.children)) appendBlock(child);
  return paragraphs.length > 0 ? paragraphs : [new Paragraph({ children: [] })];
}

export async function exportToDocx(
  title: string,
  content: string,
  subtitle?: string,
  date?: string,
  renderedHtml?: string,
): Promise<void> {
  const children: Paragraph[] = [];

  children.push(
    new Paragraph({
      text: title,
      heading: HeadingLevel.TITLE,
    })
  );

  children.push(new Paragraph({ children: [] }));
  children.push(
    new Paragraph({
      children: [
        new TextRun({ text: "GerClaw 老年AI诊疗平台", bold: true }),
      ],
    })
  );
  if (subtitle) {
    children.push(new Paragraph({ text: subtitle }));
  }
  children.push(
    new Paragraph({
      text: `生成时间：${date ?? new Date().toLocaleString("zh-CN")}`,
    })
  );
  children.push(new Paragraph({ children: [] }));

  children.push(
    ...renderedHtmlToDocxParagraphs(
      renderedHtml ?? artifactMarkdownToRichHtml(content),
    ),
  );

  const doc = new Document({
    sections: [
      {
        properties: {},
        children,
      },
    ],
  });

  const blob = await Packer.toBlob(doc);
  saveAs(blob, `${sanitizeFilename(title)}.docx`);
}

export async function exportConversationToDocx(
  title: string,
  messages: { role: "user" | "assistant"; content: string }[],
  date?: string
): Promise<void> {
  const children: Paragraph[] = [];

  children.push(
    new Paragraph({
      text: title,
      heading: HeadingLevel.TITLE,
    })
  );
  children.push(new Paragraph({ children: [] }));
  children.push(
    new Paragraph({
      children: [
        new TextRun({ text: "GerClaw 老年AI诊疗平台 — 对话记录", bold: true }),
      ],
    })
  );
  children.push(
    new Paragraph({
      text: `导出时间：${date ?? new Date().toLocaleString("zh-CN")}`,
    })
  );
  children.push(new Paragraph({ children: [] }));

  for (const msg of messages) {
    const label = msg.role === "user" ? "👤 用户" : "🩺 GerClaw";
    children.push(
      new Paragraph({
        text: label,
        heading: HeadingLevel.HEADING_3,
      })
    );
    children.push(
      ...renderedHtmlToDocxParagraphs(
        artifactMarkdownToRichHtml(msg.content.trim()),
      ),
    );
    children.push(new Paragraph({ children: [] }));
  }
  children.push(new Paragraph({ children: [] }));
  children.push(
    new Paragraph({
      children: [
        new TextRun({ text: `医疗免责声明：${MEDICAL_EXPORT_DISCLAIMER}`, italics: true, color: "666666" }),
      ],
    })
  );

  const doc = new Document({
    sections: [
      {
        properties: {},
        children,
      },
    ],
  });

  const blob = await Packer.toBlob(doc);
  saveAs(blob, `${sanitizeFilename(title)}.docx`);
}
