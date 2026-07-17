export interface ExportConfig {
  title: string;
  content: string;
  subtitle?: string;
  date?: string;
}

export const MEDICAL_EXPORT_DISCLAIMER = "本内容由 GerClaw AI 生成，仅供参考，不能替代专业医疗诊断和治疗建议。身体不适请及时就医，用药请遵医嘱。";
const DISCLAIMER = `> ⚠️ **医疗免责声明**：${MEDICAL_EXPORT_DISCLAIMER}`;

export function buildMarkdownDocument(config: ExportConfig): string {
  const date = config.date ?? new Date().toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

  const parts: string[] = [];

  parts.push(`# ${config.title}`);
  parts.push("");
  parts.push(`**GerClaw 老年AI诊疗平台**`);
  if (config.subtitle) {
    parts.push(`**${config.subtitle}**`);
  }
  parts.push(`**生成时间：** ${date}`);
  parts.push("");
  parts.push("---");
  parts.push("");
  parts.push(config.content.trim());
  parts.push("");
  parts.push("---");
  parts.push("");
  parts.push(DISCLAIMER);
  parts.push("");

  return parts.join("\n");
}

export function buildConversationMarkdown(
  title: string,
  messages: { role: "user" | "assistant"; content: string }[],
  date?: string
): string {
  const parts: string[] = [];

  parts.push(`# ${title}`);
  parts.push("");
  parts.push(`**GerClaw 老年AI诊疗平台 — 对话记录**`);
  parts.push(`**导出时间：** ${date ?? new Date().toLocaleString("zh-CN")}`);
  parts.push("");
  parts.push("---");
  parts.push("");

  for (const msg of messages) {
    const label = msg.role === "user" ? "👤 用户" : "🩺 GerClaw";
    parts.push(`### ${label}`);
    parts.push("");
    parts.push(msg.content.trim());
    parts.push("");
  }

  parts.push("---");
  parts.push("");
  parts.push(DISCLAIMER);
  parts.push("");

  return parts.join("\n");
}

export function buildConversationPlainText(
  title: string,
  messages: { role: "user" | "assistant"; content: string }[],
  date?: string
): string {
  const parts = [
    title,
    "GerClaw 老年AI诊疗平台 — 对话记录",
    `导出时间：${date ?? new Date().toLocaleString("zh-CN")}`,
    "",
  ];
  for (const message of messages) {
    parts.push(message.role === "user" ? "用户：" : "GerClaw：");
    parts.push(message.content.trim(), "");
  }
  parts.push("医疗免责声明：", MEDICAL_EXPORT_DISCLAIMER, "");
  return parts.join("\n");
}
