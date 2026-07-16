import { z } from "zod";

export class PayloadLimitError extends Error {
  constructor() {
    super("payload exceeds configured byte limit");
    this.name = "PayloadLimitError";
  }
}

/**
 * Give MinerU an opaque filename: a user's original filename can itself be
 * identifying information, while the provider only needs a supported suffix.
 */
export function opaqueProviderFileName(extension: string, opaqueId: string): string {
  const normalizedExtension = extension.trim().toLowerCase();
  if (!/^[a-z0-9]{1,10}$/.test(normalizedExtension)) {
    throw new Error("provider filename extension is invalid");
  }
  if (!/^[a-z0-9-]{8,64}$/i.test(opaqueId)) {
    throw new Error("provider filename identifier is invalid");
  }
  return `document-${opaqueId}.${normalizedExtension}`;
}

export async function readStreamWithLimit(
  stream: ReadableStream<Uint8Array> | null,
  maxBytes: number,
  declaredLength?: string | null
): Promise<Uint8Array<ArrayBuffer>> {
  const parsedLength = declaredLength ? Number.parseInt(declaredLength, 10) : undefined;
  if (parsedLength !== undefined && Number.isFinite(parsedLength) && parsedLength > maxBytes) {
    throw new PayloadLimitError();
  }
  if (!stream) return new Uint8Array(new ArrayBuffer(0));

  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) {
        await reader.cancel();
        throw new PayloadLimitError();
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  const combined = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    combined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return combined;
}

const submitSchema = z.object({
  code: z.number(),
  data: z.object({
    task_id: z.string().min(1),
    file_url: z.string().url(),
  }),
  msg: z.string().optional(),
});

const pollSchema = z.object({
  code: z.number(),
  data: z.object({
    state: z.enum(["waiting-file", "uploading", "pending", "running", "done", "failed"]),
    markdown_url: z.string().url().optional(),
    err_msg: z.string().optional(),
  }),
  msg: z.string().optional(),
});

export function assertAllowedProviderUrl(url: string, allowedHosts: ReadonlySet<string>): URL {
  const parsed = new URL(url);
  if (parsed.protocol !== "https:" || !allowedHosts.has(parsed.hostname.toLowerCase())) {
    throw new Error("provider returned a URL outside the configured allowlist");
  }
  return parsed;
}

export function parseSubmitResponse(value: unknown) {
  const parsed = submitSchema.safeParse(value);
  if (!parsed.success || parsed.data.code !== 0) {
    throw new Error("invalid document submit response");
  }
  return {
    taskId: parsed.data.data.task_id,
    fileUrl: parsed.data.data.file_url,
  };
}

export function parsePollResponse(value: unknown) {
  const parsed = pollSchema.safeParse(value);
  if (!parsed.success || parsed.data.code !== 0) {
    throw new Error("invalid document poll response");
  }
  return {
    state: parsed.data.data.state,
    markdownUrl: parsed.data.data.markdown_url,
    error: parsed.data.data.err_msg,
  };
}
