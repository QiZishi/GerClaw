import type { GerclawApiError } from "./client";

/**
 * Projects a transport/runtime failure into the only wording that belongs in
 * the conversation.  Raw provider responses, trace identifiers, retry
 * checkpoints and policy codes are useful in production logs, not to people
 * reading a consultation.
 */
export function presentChatError(
  error: Pick<GerclawApiError, "code" | "status">,
): string {
  const code = error.code.toUpperCase();

  if (
    /(?:POLICY|SENSITIVE|MODERATION|CONTENT(?:_|-)?(?:FILTER|BLOCK)|PRIVACY)/.test(
      code,
    )
  ) {
    return "你的需求中有目前无法处理的敏感内容，请调整后再试";
  }

  if (
    error.status >= 500 ||
    /(?:PROVIDER|MODEL|NETWORK|TIMEOUT|UNAVAILABLE|CONNECTION|STREAM|TRANSPORT|UPSTREAM|RATE_LIMIT|CLIENT_FAILED|REQUEST_FAILED)/.test(
      code,
    )
  ) {
    return "服务暂时不稳定，这次回答没有完整生成。请稍后重试";
  }

  return "这次回答没有完整生成，请重试";
}
