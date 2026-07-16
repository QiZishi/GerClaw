import { NextRequest } from "next/server";
import {
  assertAllowedProviderUrl,
  PayloadLimitError,
  parsePollResponse,
  parseSubmitResponse,
  readStreamWithLimit,
} from "@/server/mineru-contract";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_FILE_SIZE = 10 * 1024 * 1024;
const MAX_MULTIPART_SIZE = MAX_FILE_SIZE + 256 * 1024;
const MAX_PROVIDER_JSON_SIZE = 256 * 1024;
const MAX_MARKDOWN_SIZE = 5 * 1024 * 1024;
const POLL_INTERVAL_MS = 2_000;
const REQUEST_TIMEOUT_MS = 60_000;
const SUPPORTED_EXTENSIONS = new Set([
  "pdf",
  "docx",
  "png",
  "jpg",
  "jpeg",
  "gif",
  "webp",
]);
const SUPPORTED_MIME_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
]);

interface ParseResponse {
  success: boolean;
  markdown?: string;
  error?: string;
  fileName: string;
}

function errorResponse(error: string, fileName: string, status: number) {
  return Response.json(
    { success: false, error, fileName } satisfies ParseResponse,
    { status }
  );
}

function getProviderConfig() {
  const baseUrl = (process.env.MINERU_URL ?? process.env.MINERU_API_BASE_URL ?? "")
    .trim()
    .replace(/\/$/, "");
  const allowedHosts = new Set(
    (process.env.MINERU_ALLOWED_HOSTS ?? "")
      .split(",")
      .map((host) => host.trim().toLowerCase())
      .filter(Boolean)
  );
  return {
    baseUrl,
    allowedHosts,
    apiKey: (process.env.MINERU_API_KEY ?? "").trim(),
  };
}

function providerHeaders(apiKey: string): HeadersInit {
  return apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) {
    throw new DOMException("document parsing cancelled", "AbortError");
  }
}

async function fetchWithTimeout(url: string, init?: RequestInit, requestSignal?: AbortSignal) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const abortFromRequest = () => controller.abort(requestSignal?.reason);
  if (requestSignal?.aborted) {
    abortFromRequest();
  } else {
    requestSignal?.addEventListener("abort", abortFromRequest, { once: true });
  }
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timeoutId);
    requestSignal?.removeEventListener("abort", abortFromRequest);
  }
}

async function waitForPoll(signal?: AbortSignal): Promise<void> {
  throwIfAborted(signal);
  await new Promise<void>((resolve, reject) => {
    const state: { timeoutId?: ReturnType<typeof setTimeout> } = {};
    const abort = () => {
      if (state.timeoutId) clearTimeout(state.timeoutId);
      cleanup();
      reject(new DOMException("document parsing cancelled", "AbortError"));
    };
    const cleanup = () => signal?.removeEventListener("abort", abort);
    state.timeoutId = setTimeout(() => {
      cleanup();
      resolve();
    }, POLL_INTERVAL_MS);
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) abort();
  });
}

async function readJsonResponse(response: Response): Promise<unknown> {
  const bytes = await readStreamWithLimit(
    response.body,
    MAX_PROVIDER_JSON_SIZE,
    response.headers.get("content-length")
  );
  return JSON.parse(new TextDecoder().decode(bytes));
}

export async function POST(request: NextRequest): Promise<Response> {
  let fileName = "";
  const traceId = crypto.randomUUID();

  try {
    const contentType = request.headers.get("content-type") ?? "";
    if (!contentType.toLowerCase().startsWith("multipart/form-data")) {
      return errorResponse("上传请求格式不正确", "", 400);
    }
    const requestBytes = await readStreamWithLimit(
      request.body,
      MAX_MULTIPART_SIZE,
      request.headers.get("content-length")
    );
    const boundedRequest = new Request(request.url, {
      method: "POST",
      headers: { "Content-Type": contentType },
      body: requestBytes.buffer,
    });
    const formData = await boundedRequest.formData();
    const entry = formData.get("file");
    if (!(entry instanceof File)) {
      return errorResponse("请选择需要解析的文件", "", 400);
    }

    fileName = entry.name.trim();
    const extension = fileName.split(".").pop()?.toLowerCase() ?? "";
    if (
      !fileName ||
      !SUPPORTED_EXTENSIONS.has(extension) ||
      !SUPPORTED_MIME_TYPES.has(entry.type)
    ) {
      return errorResponse("MinerU 不支持该文件格式，请上传 PDF、Word 或常见图片", fileName, 415);
    }
    if (entry.size <= 0 || entry.size > MAX_FILE_SIZE) {
      return errorResponse("文件为空或超过 10MB 限制", fileName, 413);
    }

    const config = getProviderConfig();
    if (!config.baseUrl || config.allowedHosts.size === 0) {
      return errorResponse("文档解析服务暂时不可用，请稍后重试；图片仍可直接上传", fileName, 503);
    }
    assertAllowedProviderUrl(config.baseUrl, config.allowedHosts);

    const markdown = await parseWithMinerU(entry, config, request.signal);
    console.info("[GerClaw][Document] parse completed", { traceId, fileName });
    return Response.json({ success: true, markdown, fileName } satisfies ParseResponse);
  } catch (error) {
    if (error instanceof PayloadLimitError) {
      return errorResponse("上传内容超过 10MB 限制", fileName, 413);
    }
    console.error("[GerClaw][Document] parse failed", {
      traceId,
      fileName,
      error: error instanceof Error ? error.message : "unknown error",
    });
    const message =
      error instanceof Error && error.name === "AbortError"
        ? "文档解析超时，请稍后重试"
        : "文档解析服务暂时不可用，请稍后重试；图片仍可直接上传";
    return errorResponse(message, fileName, 503);
  }
}

async function parseWithMinerU(
  file: File,
  config: ReturnType<typeof getProviderConfig>,
  requestSignal?: AbortSignal,
): Promise<string> {
  throwIfAborted(requestSignal);
  const submitUrl = `${config.baseUrl}/parse/file`;
  const submitResponse = await fetchWithTimeout(submitUrl, {
    method: "POST",
    headers: {
      ...providerHeaders(config.apiKey),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      file_name: file.name,
      language: "ch",
      enable_table: true,
      is_ocr: false,
      enable_formula: true,
    }),
  }, requestSignal);
  if (!submitResponse.ok) throw new Error(`submit failed (${submitResponse.status})`);

  const submission = parseSubmitResponse(await readJsonResponse(submitResponse));
  assertAllowedProviderUrl(submission.fileUrl, config.allowedHosts);

  const uploadResponse = await fetchWithTimeout(submission.fileUrl, {
    method: "PUT",
    body: await file.arrayBuffer(),
  }, requestSignal);
  if (!uploadResponse.ok) throw new Error(`upload failed (${uploadResponse.status})`);

  return pollForResult(submission.taskId, config, requestSignal);
}

async function pollForResult(
  taskId: string,
  config: ReturnType<typeof getProviderConfig>,
  requestSignal?: AbortSignal,
): Promise<string> {
  const deadline = Date.now() + REQUEST_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await waitForPoll(requestSignal);
    const response = await fetchWithTimeout(
      `${config.baseUrl}/parse/${encodeURIComponent(taskId)}`,
      { headers: providerHeaders(config.apiKey) },
      requestSignal,
    );
    if (!response.ok) throw new Error(`poll failed (${response.status})`);

    const result = parsePollResponse(await readJsonResponse(response));
    if (result.state === "failed") {
      throw new Error(result.error || "provider reported failure");
    }
    if (result.state !== "done") continue;
    if (!result.markdownUrl) throw new Error("provider returned no markdown URL");

    assertAllowedProviderUrl(result.markdownUrl, config.allowedHosts);
    const markdownResponse = await fetchWithTimeout(result.markdownUrl, undefined, requestSignal);
    if (!markdownResponse.ok) {
      throw new Error(`markdown download failed (${markdownResponse.status})`);
    }
    const markdownBytes = await readStreamWithLimit(
      markdownResponse.body,
      MAX_MARKDOWN_SIZE,
      markdownResponse.headers.get("content-length")
    );
    const markdown = new TextDecoder().decode(markdownBytes).trim();
    if (!markdown) throw new Error("provider returned empty markdown");
    return markdown;
  }
  throw new DOMException("document parsing timed out", "AbortError");
}
