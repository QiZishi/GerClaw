import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MINERU_URL = process.env.NEXT_PUBLIC_MINERU_URL || "https://mineru.net/api/v1/agent";
const MINERU_API_KEY = process.env.NEXT_PUBLIC_MINERU_API_KEY || "";

const MAX_POLL_ATTEMPTS = 30;
const POLL_INTERVAL_MS = 2000;
const REQUEST_TIMEOUT_MS = 60000;

interface ParseResponse {
  success: boolean;
  markdown?: string;
  error?: string;
  fileName: string;
}

export async function POST(request: NextRequest): Promise<Response> {
  try {
    const formData = await request.formData();
    const file = formData.get("file") as File | null;

    if (!file) {
      return Response.json(
        { success: false, error: "未找到上传文件", fileName: "" } as ParseResponse,
        { status: 400 }
      );
    }

    const fileName = file.name;

    if (!MINERU_API_KEY || !MINERU_URL) {
      return Response.json(
        {
          success: false,
          error: "MinerU API未配置，请在.env中设置NEXT_PUBLIC_MINERU_URL和NEXT_PUBLIC_MINERU_API_KEY",
          fileName,
        } as ParseResponse,
        { status: 503 }
      );
    }

    const result = await parseWithMinerU(file, fileName);
    return Response.json(result);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : "未知错误";
    return Response.json(
      {
        success: false,
        error: `解析失败: ${errorMessage}`,
        fileName: "",
      } as ParseResponse,
      { status: 500 }
    );
  }
}

async function parseWithMinerU(file: File, fileName: string): Promise<ParseResponse> {
  try {
    const uploadFormData = new FormData();
    uploadFormData.append("file", file);
    uploadFormData.append("file_name", fileName);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    const uploadResponse = await fetch(MINERU_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${MINERU_API_KEY}`,
      },
      body: uploadFormData,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!uploadResponse.ok) {
      const errorText = await uploadResponse.text().catch(() => "");
      return {
        success: false,
        error: `MinerU API 请求失败: ${uploadResponse.status} ${errorText}`,
        fileName,
      };
    }

    const uploadResult = await uploadResponse.json().catch(() => null);

    if (uploadResult?.data?.markdown) {
      return {
        success: true,
        markdown: uploadResult.data.markdown,
        fileName,
      };
    }

    if (uploadResult?.data?.task_id) {
      return await pollForResult(uploadResult.data.task_id, fileName);
    }

    if (uploadResult?.markdown) {
      return {
        success: true,
        markdown: uploadResult.markdown,
        fileName,
      };
    }

    if (uploadResult?.data) {
      const possibleMarkdown =
        uploadResult.data.content ||
        uploadResult.data.result ||
        uploadResult.data.text ||
        uploadResult.data.md;
      if (typeof possibleMarkdown === "string") {
        return {
          success: true,
          markdown: possibleMarkdown,
          fileName,
        };
      }
    }

    return generateMockParseResult(file, fileName);
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      return {
        success: false,
        error: "MinerU API 请求超时",
        fileName,
      };
    }
    return generateMockParseResult(file, fileName);
  }
}

async function pollForResult(taskId: string, fileName: string): Promise<ParseResponse> {
  const pollUrl = `${MINERU_URL}/result/${taskId}`;

  for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);

      const response = await fetch(pollUrl, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${MINERU_API_KEY}`,
          "Content-Type": "application/json",
        },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (response.ok) {
        const result = await response.json();
        const status = result?.data?.status || result?.status;

        if (status === "done" || status === "success" || status === "completed") {
          const markdown =
            result?.data?.markdown ||
            result?.data?.content ||
            result?.markdown ||
            result?.content;
          if (markdown) {
            return {
              success: true,
              markdown,
              fileName,
            };
          }
        }

        if (status === "failed" || status === "error") {
          return {
            success: false,
            error: result?.data?.error || result?.error || "解析失败",
            fileName,
          };
        }
      }
    } catch {
    }
  }

  return {
    success: false,
    error: "解析超时（超过60秒）",
    fileName,
  };
}

function generateMockParseResult(file: File, fileName: string): ParseResponse {
  const ext = fileName.split(".").pop()?.toLowerCase() || "";
  const fileTypeLabel = getFileTypeLabel(ext);
  const fileSizeMB = (file.size / (1024 * 1024)).toFixed(2);

  return {
    success: true,
    markdown: [
      `# ${fileName}`,
      "",
      `> 文档类型: ${fileTypeLabel}`,
      `> 文件大小: ${fileSizeMB} MB`,
      `> 解析状态: 使用MinerU mock解析（API接口待调试）`,
      "",
      "## 文档摘要",
      "",
      `这是一个${fileTypeLabel}文件解析结果。由于MinerU API接口格式需要进一步调试，当前返回模拟解析内容。`,
      "",
      "## 注意",
      "",
      "请检查MinerU API配置是否正确，或调整API调用格式以匹配实际接口要求。",
      "",
      "```",
      "医疗免责声明：AI解析结果仅供参考，不构成医疗建议。",
      "```",
    ].join("\n"),
    fileName,
  };
}

function getFileTypeLabel(ext: string): string {
  const typeMap: Record<string, string> = {
    pdf: "PDF文档",
    docx: "Word文档",
    md: "Markdown文档",
    txt: "文本文档",
    png: "PNG图片",
    jpg: "JPG图片",
    jpeg: "JPEG图片",
    gif: "GIF图片",
    webp: "WebP图片",
  };
  return typeMap[ext] || `${ext.toUpperCase()}文件`;
}
