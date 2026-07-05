export class ApiError extends Error {
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

export class NetworkError extends ApiError {
  constructor(message: string, traceId?: string) {
    super(message, "NETWORK_ERROR", undefined, true, traceId);
    this.name = "NetworkError";
  }
}

export class TimeoutError extends ApiError {
  constructor(message: string, traceId?: string) {
    super(message, "TIMEOUT", undefined, true, traceId);
    this.name = "TimeoutError";
  }
}

export class RateLimitError extends ApiError {
  constructor(message: string, status?: number, traceId?: string) {
    super(message, "RATE_LIMIT", status, true, traceId);
    this.name = "RateLimitError";
  }
}

export class AuthenticationError extends ApiError {
  constructor(message: string, status?: number, traceId?: string) {
    super(message, "AUTHENTICATION_ERROR", status, false, traceId);
    this.name = "AuthenticationError";
  }
}

export class ServerError extends ApiError {
  constructor(message: string, status?: number, traceId?: string) {
    super(message, "SERVER_ERROR", status, true, traceId);
    this.name = "ServerError";
  }
}

export class ClientError extends ApiError {
  constructor(message: string, status?: number, traceId?: string) {
    super(message, "CLIENT_ERROR", status, false, traceId);
    this.name = "ClientError";
  }
}

export function generateTraceId(): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).substring(2, 10);
  return `trace_${timestamp}_${random}`;
}

export async function fetchWithTimeout(
  url: string,
  options: RequestInit & { timeoutMs?: number },
  timeoutMs: number = 30000
): Promise<Response> {
  const controller = new AbortController();
  const effectiveTimeout = options.timeoutMs ?? timeoutMs;
  const timeoutId = setTimeout(() => controller.abort(), effectiveTimeout);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    return response;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new TimeoutError(`请求超时（${effectiveTimeout}ms）`);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function withRetry<T>(
  fn: () => Promise<T>,
  options?: {
    maxRetries?: number;
    baseDelayMs?: number;
    maxDelayMs?: number;
    retryOn?: (error: unknown) => boolean;
  }
): Promise<T> {
  const maxRetries = options?.maxRetries ?? 2;
  const baseDelayMs = options?.baseDelayMs ?? 1000;
  const maxDelayMs = options?.maxDelayMs ?? 10000;
  const retryOn = options?.retryOn ?? isRetriableError;

  let lastError: unknown;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      if (attempt >= maxRetries || !retryOn(error)) {
        throw error;
      }

      const delay = Math.min(baseDelayMs * Math.pow(2, attempt), maxDelayMs);
      const jitter = Math.random() * delay * 0.1;
      await new Promise((resolve) => setTimeout(resolve, delay + jitter));
    }
  }

  throw lastError;
}

function isRetriableError(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.retriable;
  }
  return false;
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

export function classifyHttpError(
  status: number,
  message: string,
  traceId: string
): ApiError {
  if (status === 401 || status === 403) {
    return new AuthenticationError(message || "认证失败", status, traceId);
  }
  if (status === 429) {
    return new RateLimitError(message || "请求频率过高", status, traceId);
  }
  if (status >= 500 && status < 600) {
    return new ServerError(message || `服务器错误 (${status})`, status, traceId);
  }
  if (status >= 400 && status < 500) {
    return new ClientError(message || `客户端错误 (${status})`, status, traceId);
  }
  return new ApiError(message || `HTTP错误 (${status})`, "HTTP_ERROR", status, false, traceId);
}
