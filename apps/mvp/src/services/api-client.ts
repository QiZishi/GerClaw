class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public status?: number,
    public retriable: boolean = false,
    public traceId?: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

class NetworkError extends ApiError {
  constructor(message: string, traceId?: string) {
    super(message, "NETWORK_ERROR", undefined, true, traceId);
    this.name = "NetworkError";
  }
}

class TimeoutError extends ApiError {
  constructor(message: string, traceId?: string) {
    super(message, "TIMEOUT", undefined, true, traceId);
    this.name = "TimeoutError";
  }
}

export function generateTraceId(): string {
  // The governed BFF only forwards opaque trace IDs with this exact shape.
  // UUID v4 supplies 128 bits of browser-generated correlation entropy without
  // encoding timestamps or user information.
  return `trace_${crypto.randomUUID().replaceAll("-", "")}`;
}

export function classifyError(error: unknown, traceId: string): ApiError {
  if (error instanceof ApiError) {
    error.traceId = error.traceId ?? traceId;
    return error;
  }

  if (error instanceof TypeError && error.message.includes("fetch")) {
    return new NetworkError(`网络连接失败：${error.message}`, traceId);
  }

  if (error instanceof DOMException && error.name === "AbortError") {
    return new TimeoutError("请求超时", traceId);
  }

  if (error instanceof Error) {
    return new ApiError(error.message, "UNKNOWN_ERROR", undefined, false, traceId);
  }

  return new ApiError("未知错误", "UNKNOWN_ERROR", undefined, false, traceId);
}
