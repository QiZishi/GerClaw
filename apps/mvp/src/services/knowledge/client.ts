export interface KnowledgeChunk {
  id: string;
  title: string;
  category: string;
  content: string;
  filePath: string;
}

export interface RetrieveResult {
  success: boolean;
  chunks: KnowledgeChunk[];
  total: number;
  error?: string;
}

export async function retrieveKnowledge(
  query: string,
  maxResults: number = 3
): Promise<RetrieveResult> {
  try {
    const response = await fetch("/api/knowledge/retrieve", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query, maxResults }),
    });

    if (!response.ok) {
      return { success: false, chunks: [], total: 0, error: "检索请求失败" };
    }

    const data = await response.json();
    return data;
  } catch {
    return { success: false, chunks: [], total: 0, error: "检索服务不可用" };
  }
}
