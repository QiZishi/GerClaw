import { z } from "zod";

export interface ParseResult {
  markdown: string;
  source: "mineru" | "local-text";
}

const parseResponseSchema = z.object({
  success: z.boolean(),
  markdown: z.string().optional(),
  error: z.string().optional(),
  fileName: z.string(),
});

export async function parseFile(file: File, signal?: AbortSignal): Promise<ParseResult> {
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (extension === "md" || extension === "txt") {
    if (file.size > 1024 * 1024) throw new Error("文本文件超过 1MB 限制");
    const markdown = (await file.text()).trim();
    if (!markdown) throw new Error("文本文件内容为空");
    return { markdown, source: "local-text" };
  }

  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/api/mineru/parse", {
    method: "POST",
    body: formData,
    signal,
  });

  if (!response.ok) {
    let errorMessage = `解析请求失败: ${response.status}`;
    try {
      const errorData = parseResponseSchema.safeParse(await response.json());
      if (errorData.success && errorData.data.error) {
        errorMessage = errorData.data.error;
      }
    } catch {
    }
    throw new Error(errorMessage);
  }

  const parsed = parseResponseSchema.safeParse(await response.json().catch(() => null));
  if (!parsed.success) {
    throw new Error("文档解析服务返回了无法识别的数据");
  }
  const data = parsed.data;

  if (!data.success) {
    throw new Error(data.error || "文件解析失败");
  }

  if (!data.markdown?.trim()) throw new Error("文档解析结果为空");
  return { markdown: data.markdown, source: "mineru" };
}
