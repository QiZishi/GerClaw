export class SearchRequestError extends Error {
  readonly retryable: boolean;

  constructor(message: string, retryable: boolean) {
    super(message);
    this.name = "SearchRequestError";
    this.retryable = retryable;
  }
}

export function statusIsRetryable(status: number): boolean {
  return status === 408 || status === 429 || status >= 500;
}

export async function withTransientRetry<T>(
  operation: () => Promise<T>
): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    if (!(error instanceof SearchRequestError) || !error.retryable) throw error;
    return operation();
  }
}

export async function withPrimaryFallback<T>(
  primary: () => Promise<T>,
  fallback: () => Promise<T>
): Promise<{ value: T; fallbackUsed: boolean }> {
  try {
    return { value: await withTransientRetry(primary), fallbackUsed: false };
  } catch {
    return { value: await withTransientRetry(fallback), fallbackUsed: true };
  }
}
