import type { Message, MessageBlock } from "@/types";

export interface ArtifactDraftSource {
  requestId: string;
  messageId: string;
  runId: string | null;
  title: string;
  markdown: string;
}

function textBlocks(blocks: MessageBlock[]): string {
  return blocks
    .filter((block): block is Extract<MessageBlock, { kind: "text" }> => block.kind === "text")
    .map((block) => block.content.trim())
    .filter(Boolean)
    .join("\n\n")
    .trim();
}

export function artifactTitleFromMarkdown(markdown: string): string {
  const firstMeaningfulLine = markdown
    .split(/\r?\n/)
    .map((line) => line.replace(/^#{1,6}\s+/, "").trim())
    .find(Boolean);
  if (!firstMeaningfulLine) return "AI 健康建议";
  const normalized = firstMeaningfulLine.replace(/[*_`~[\]]/g, "").trim();
  return normalized.length > 48 ? `${normalized.slice(0, 48).trim()}…` : normalized;
}

export function artifactDraftFromMessage(
  message: Message,
  requestId: string,
): ArtifactDraftSource {
  const markdown = textBlocks(message.blocks);
  return {
    requestId,
    messageId: message.id,
    runId: message.executionRunId ?? null,
    title: artifactTitleFromMarkdown(markdown),
    markdown,
  };
}
