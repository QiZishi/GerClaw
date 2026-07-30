import type { Message } from "@/types";

type DisclaimerMessage = Pick<Message, "role" | "blocks">;

export function shouldShowComposerDisclaimer(
  messages: readonly DisclaimerMessage[],
  disclaimer: string,
): boolean {
  return !messages.some(
    (message) =>
      message.role === "assistant" &&
      message.blocks.some(
        (block) =>
          block.kind === "text" && block.content.includes(disclaimer),
      ),
  );
}
