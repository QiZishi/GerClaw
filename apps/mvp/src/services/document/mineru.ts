export interface ParseResult {
  markdown: string;
}

export async function parseFile(file: File): Promise<ParseResult> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/api/mineru/parse", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let errorMessage = `解析请求失败: ${response.status}`;
    try {
      const errorData = await response.json();
      if (errorData?.error) {
        errorMessage = errorData.error;
      }
    } catch {
    }
    throw new Error(errorMessage);
  }

  const data = await response.json();

  if (!data.success) {
    throw new Error(data.error || "文件解析失败");
  }

  return {
    markdown: data.markdown || "",
  };
}
