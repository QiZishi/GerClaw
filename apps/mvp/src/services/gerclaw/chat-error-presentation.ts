import type { GerclawApiError } from "./client";

/**
 * Projects a transport/runtime failure into the only wording that belongs in
 * the conversation.  Raw provider responses, trace identifiers, retry
 * checkpoints and policy codes are useful in production logs, not to people
 * reading a consultation.
 */
export function presentChatError(
  error: Pick<GerclawApiError, "code" | "status"> &
    Partial<Pick<GerclawApiError, "message">>,
): string {
  const code = error.code.toUpperCase();

  if (
    code.startsWith("CHAT_") &&
    code !== "CHAT_CLIENT_FAILED" &&
    error.message?.trim()
  ) {
    return error.message.trim();
  }

  if (error.status === 401 || /(?:AUTH_REQUIRED|AUTH_INVALID|ACCOUNT_SESSION)/.test(code)) {
    return "当前访问会话已更新，请再次发送问题。";
  }

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

export function isReaderFacingChatFallback(
  error: Pick<GerclawApiError, "code" | "message">,
): boolean {
  const code = error.code.toUpperCase();
  return (
    (code.startsWith("CHAT_") || code.startsWith("RUN_STREAM_")) &&
    Boolean(error.message.trim())
  );
}
