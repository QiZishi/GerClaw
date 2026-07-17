import {
  Document,
  Packer,
  Paragraph,
  TextRun,
  HeadingLevel,
} from "docx";
import { saveAs } from "file-saver";
import { sanitizeFilename } from "./utils";
import { MEDICAL_EXPORT_DISCLAIMER } from "./template";

function markdownToDocxParagraphs(markdown: string): Paragraph[] {
  const paragraphs: Paragraph[] = [];
  const lines = markdown.split("\n");

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      paragraphs.push(new Paragraph({ children: [] }));
      continue;
    }

    if (trimmed.startsWith("# ")) {
      paragraphs.push(
        new Paragraph({
          text: trimmed.slice(2),
          heading: HeadingLevel.HEADING_1,
        })
      );
    } else if (trimmed.startsWith("## ")) {
      paragraphs.push(
        new Paragraph({
          text: trimmed.slice(3),
          heading: HeadingLevel.HEADING_2,
        })
      );
    } else if (trimmed.startsWith("### ")) {
      paragraphs.push(
        new Paragraph({
          text: trimmed.slice(4),
          heading: HeadingLevel.HEADING_3,
        })
      );
    } else if (trimmed === "---") {
      paragraphs.push(new Paragraph({ children: [] }));
    } else if (trimmed.startsWith("> ")) {
      paragraphs.push(
        new Paragraph({
          children: [
            new TextRun({
              text: trimmed.slice(2).replace(/\*\*/g, ""),
              italics: true,
              color: "666666",
            }),
          ],
        })
      );
    } else if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      paragraphs.push(
        new Paragraph({
          children: [
            new TextRun({ text: "• " }),
            new TextRun({ text: trimmed.slice(2).replace(/\*\*/g, "") }),
          ],
        })
      );
    } else {
      const runs: TextRun[] = [];
      const parts = trimmed.split(/(\*\*[^*]+\*\*)/g);
      for (const part of parts) {
        if (part.startsWith("**") && part.endsWith("**")) {
          runs.push(new TextRun({ text: part.slice(2, -2), bold: true }));
        } else {
          runs.push(new TextRun({ text: part }));
        }
      }
      paragraphs.push(new Paragraph({ children: runs }));
    }
  }
  return paragraphs;
}

export async function exportToDocx(
  title: string,
  content: string,
  subtitle?: string,
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

  children.push(...markdownToDocxParagraphs(content));

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
    children.push(...markdownToDocxParagraphs(msg.content.trim()));
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
