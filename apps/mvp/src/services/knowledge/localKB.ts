import * as fs from "fs";
import * as path from "path";

export interface KnowledgeChunk {
  id: string;
  title: string;
  category: string;
  content: string;
  filePath: string;
}

const DEFAULT_KB_PATH = "/Users/qizs/conclusion/gerclaw/本地知识库/md";
const CHUNK_SIZE = 800;
const CHUNK_OVERLAP = 100;

let chunksCache: KnowledgeChunk[] | null = null;
let isInitializing = false;
let initPromise: Promise<KnowledgeChunk[]> | null = null;
let initStarted = false;

export function isKBInitialized(): boolean {
  return chunksCache !== null;
}

export function isKBInitializing(): boolean {
  return isInitializing;
}

function getKBPath(): string {
  return process.env.GERCLAW_KNOWLEDGE_BASE_PATH || DEFAULT_KB_PATH;
}

function extractTitleFromContent(content: string, fileName: string): string {
  const lines = content.split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("# ")) {
      return trimmed.replace(/^#\s+/, "").trim();
    }
  }
  const match = fileName.match(/MinerU_(.+?)__\d+/);
  if (match) {
    return match[1].replace(/_/g, " ").trim();
  }
  return fileName.replace(/\.md$/, "");
}

function extractCategoryFromPath(filePath: string, kbRoot: string): string {
  const relative = path.relative(kbRoot, filePath);
  const parts = relative.split(path.sep);
  if (parts.length > 0) {
    const category = parts[0];
    return category.replace(/md$|MD$/, "");
  }
  return "未分类";
}

function splitIntoChunks(content: string, fileId: string, title: string, category: string, filePath: string): KnowledgeChunk[] {
  const chunks: KnowledgeChunk[] = [];
  const cleanedContent = content.replace(/\r\n/g, "\n").trim();
  
  const sections: { heading: string; content: string }[] = [];
  const lines = cleanedContent.split("\n");
  let currentHeading = title;
  let currentContent = "";

  for (const line of lines) {
    if (/^##\s+/.test(line.trim())) {
      if (currentContent.trim()) {
        sections.push({ heading: currentHeading, content: currentContent.trim() });
      }
      currentHeading = line.trim().replace(/^##\s+/, "");
      currentContent = "";
    } else {
      currentContent += line + "\n";
    }
  }
  if (currentContent.trim()) {
    sections.push({ heading: currentHeading, content: currentContent.trim() });
  }

  let chunkIndex = 0;
  for (const section of sections) {
    const sectionText = section.content;
    if (sectionText.length === 0) continue;

    if (sectionText.length <= CHUNK_SIZE) {
      chunks.push({
        id: `${fileId}-chunk-${chunkIndex}`,
        title: section.heading,
        category,
        content: sectionText,
        filePath,
      });
      chunkIndex++;
    } else {
      let start = 0;
      while (start < sectionText.length) {
        const end = Math.min(start + CHUNK_SIZE, sectionText.length);
        let chunkText = sectionText.slice(start, end);
        
        if (end < sectionText.length) {
          const lastNewline = chunkText.lastIndexOf("\n");
          const lastPeriod = Math.max(chunkText.lastIndexOf("。"), chunkText.lastIndexOf("."));
          const splitPos = Math.max(lastNewline, lastPeriod);
          if (splitPos > CHUNK_SIZE / 2) {
            chunkText = chunkText.slice(0, splitPos + 1);
          }
        }

        chunks.push({
          id: `${fileId}-chunk-${chunkIndex}`,
          title: section.heading,
          category,
          content: chunkText.trim(),
          filePath,
        });
        chunkIndex++;
        
        start = start + chunkText.length - CHUNK_OVERLAP;
        if (start >= sectionText.length) break;
      }
    }
  }

  return chunks;
}

async function getAllMdFiles(dir: string): Promise<string[]> {
  const files: string[] = [];
  try {
    const entries = await fs.promises.readdir(dir, { withFileTypes: true });
    
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        const subFiles = await getAllMdFiles(fullPath);
        files.push(...subFiles);
      } else if (entry.isFile() && entry.name.endsWith(".md")) {
        files.push(fullPath);
      }
    }
  } catch (err) {
    console.error(`[LocalKB] 读取目录失败: ${dir}`, err);
  }
  return files;
}

async function pathExists(p: string): Promise<boolean> {
  try {
    await fs.promises.access(p);
    return true;
  } catch {
    return false;
  }
}

export function startKBInitialization(): void {
  if (initStarted) return;
  initStarted = true;
  initializeKB().catch(err => {
    console.error("[LocalKB] 后台初始化失败", err);
  });
}

async function initializeKB(): Promise<KnowledgeChunk[]> {
  if (chunksCache) return chunksCache;
  if (isInitializing && initPromise) return initPromise;

  isInitializing = true;
  initPromise = (async () => {
    const kbPath = getKBPath();
    const allChunks: KnowledgeChunk[] = [];

    try {
      const exists = await pathExists(kbPath);
      if (!exists) {
        console.warn(`[LocalKB] 知识库路径不存在: ${kbPath}`);
        chunksCache = [];
        return chunksCache;
      }

      const mdFiles = await getAllMdFiles(kbPath);
      console.log(`[LocalKB] 找到 ${mdFiles.length} 个 Markdown 文件`);

      for (let i = 0; i < mdFiles.length; i++) {
        const filePath = mdFiles[i];
        try {
          const content = await fs.promises.readFile(filePath, "utf-8");
          const fileName = path.basename(filePath);
          const title = extractTitleFromContent(content, fileName);
          const category = extractCategoryFromPath(filePath, kbPath);
          const fileId = `kb-${i}-${Date.now()}`;
          
          const fileChunks = splitIntoChunks(content, fileId, title, category, filePath);
          allChunks.push(...fileChunks);
        } catch (err) {
          console.error(`[LocalKB] 读取文件失败: ${filePath}`, err);
        }
      }

      chunksCache = allChunks;
      console.log(`[LocalKB] 知识库初始化完成，共 ${allChunks.length} 个知识块`);
      return chunksCache;
    } catch (err) {
      console.error("[LocalKB] 初始化失败", err);
      chunksCache = [];
      return chunksCache;
    } finally {
      isInitializing = false;
    }
  })();

  return initPromise;
}

function tokenize(text: string): string[] {
  const tokens: string[] = [];
  
  const chinesePattern = /[\u4e00-\u9fa5]{2,}/g;
  let match;
  while ((match = chinesePattern.exec(text)) !== null) {
    tokens.push(match[0]);
  }

  const segments = text.split(/[\s,，。.！!？?；;：:""'（）()【】\[\]、]+/);
  for (const seg of segments) {
    const trimmed = seg.trim();
    if (trimmed.length >= 2 && !/^[\u4e00-\u9fa5]{2,}$/.test(trimmed)) {
      tokens.push(trimmed.toLowerCase());
    }
  }

  const result: string[] = [];
  for (let i = 0; i < text.length - 1; i++) {
    const char1 = text[i];
    const char2 = text[i + 1];
    if (/[\u4e00-\u9fa5]/.test(char1) && /[\u4e00-\u9fa5]/.test(char2)) {
      result.push(char1 + char2);
    }
  }

  return [...new Set([...tokens, ...result])];
}

function calculateScore(chunk: KnowledgeChunk, query: string, categoryFilter?: string): number {
  if (categoryFilter && chunk.category !== categoryFilter) {
    return 0;
  }

  const contentLower = chunk.content.toLowerCase();
  const titleLower = chunk.title.toLowerCase();
  const categoryLower = chunk.category.toLowerCase();
  const queryLower = query.toLowerCase();
  
  let score = 0;
  const tokens = tokenize(queryLower);

  for (const token of tokens) {
    if (token.length < 2) continue;
    const contentMatches = (contentLower.match(new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g")) || []).length;
    score += contentMatches * 1;
    
    const titleMatches = (titleLower.match(new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g")) || []).length;
    score += titleMatches * 3;
    
    if (categoryLower.includes(token)) {
      score += 5;
    }
  }

  if (contentLower.includes(queryLower)) {
    score += 10;
  }
  if (titleLower.includes(queryLower)) {
    score += 15;
  }

  return score;
}

export async function retrieveLocalKnowledge(
  query: string,
  maxResults: number = 5,
  category?: string
): Promise<{ chunks: KnowledgeChunk[]; total: number }> {
  const chunks = await initializeKB();
  
  if (!query.trim()) {
    return { chunks: chunks.slice(0, maxResults), total: chunks.length };
  }

  const scoredChunks = chunks.map(chunk => ({
    chunk,
    score: calculateScore(chunk, query, category),
  }));

  const filtered = scoredChunks
    .filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, maxResults)
    .map(item => item.chunk);

  return {
    chunks: filtered,
    total: chunks.length,
  };
}

export function getKBCategories(): string[] {
  const kbPath = getKBPath();
  const categories: string[] = [];
  try {
    if (fs.existsSync(kbPath)) {
      const entries = fs.readdirSync(kbPath, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isDirectory()) {
          categories.push(entry.name.replace(/md$|MD$/, ""));
        }
      }
    }
  } catch {
  }
  return categories;
}

export async function ensureKBInitialized(): Promise<void> {
  await initializeKB();
}
