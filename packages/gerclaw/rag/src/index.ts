/** Product RAG consumer: shared medical corpus + account-private library + SiliconFlow rerank. */
import { readFile } from 'node:fs/promises'
import { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import {
  GerclawRag,
  type GerclawLibraryDocument,
  type GerclawLibraryHit,
  type GerclawRagHit,
  type GerclawRagStatus,
} from '@gerclaw/library'

export interface Config {
  rerankApiKey?: string
  rerankUrl?: string
  rerankModel?: string
}

export class GerclawRagProvider extends GerclawRag {
  static inject = ['gerclawLibrary', 'gerclawSharedKnowledge']
  static Config: z<Config> = z.object({
    rerankApiKey: z.string().required(),
    rerankUrl: z.string().required(),
    rerankModel: z.string().required(),
  })

  private readonly controller = new AbortController()

  constructor(ctx: Context, private readonly config: Config) {
    super(ctx)
    ctx.effect(() => () => {
      this.controller.abort()
    }, 'gerclaw.rag.requests')
  }

  status(): GerclawRagStatus {
    return this.ctx.gerclawSharedKnowledge.status()
  }

  private signal(signal?: AbortSignal): AbortSignal {
    return signal ? AbortSignal.any([signal, this.controller.signal]) : this.controller.signal
  }

  private async rerank(
    query: string,
    candidates: readonly GerclawRagHit[],
    topK: number,
    signal?: AbortSignal,
  ): Promise<GerclawRagHit[]> {
    if (candidates.length === 0) return []
    const response = await fetch(`${this.config.rerankUrl?.replace(/\/$/u, '')}/rerank`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.config.rerankApiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: this.config.rerankModel,
        query,
        documents: candidates.map(hit => hit.snippet),
        top_n: Math.min(topK, candidates.length),
        return_documents: false,
      }),
      signal: this.signal(signal),
    })
    if (!response.ok) throw new Error(`SiliconFlow rerank 请求失败（${response.status}）`)
    const payload = await response.json() as {
      results?: Array<{ index?: number; relevance_score?: number }>
    }
    if (!payload.results?.length) throw new Error('SiliconFlow rerank 没有返回排序结果')
    return payload.results.map((row) => {
      const hit = candidates[row.index ?? -1]
      if (!hit) throw new Error('SiliconFlow rerank 返回了无效索引')
      return { ...hit, score: row.relevance_score ?? 0 }
    })
  }

  async search(query: string, topK = 8, signal?: AbortSignal): Promise<GerclawRagHit[]> {
    const requestSignal = this.signal(signal)
    requestSignal.throwIfAborted()
    const limit = Math.max(topK, 20)
    // dsh-library invokes the configured embedding provider for each search.
    // Keep the shared and private queries sequential so one account request
    // never creates competing SiliconFlow embedding jobs under the same key.
    let shared: GerclawRagHit[]
    try {
      shared = await this.ctx.gerclawSharedKnowledge.search(query, limit, requestSignal)
    } catch (error) {
      throw new Error(`共享医学知识库检索失败：${error instanceof Error ? error.message : '未知错误'}`, { cause: error })
    }
    let privateHits: GerclawLibraryHit[]
    try {
      privateHits = await this.ctx.gerclawLibrary.search(query, limit, requestSignal)
    } catch (error) {
      throw new Error(`当前账号资料检索失败：${error instanceof Error ? error.message : '未知错误'}`, { cause: error })
    }
    const user = privateHits.map(hit => ({ ...hit, origin: 'user' as const }))
    return this.rerank(query, [...shared, ...user], topK, requestSignal)
  }

  async addUserDocument(path: string, name: string): Promise<GerclawLibraryDocument> {
    const content = await readFile(path, 'utf8')
    return this.ctx.gerclawLibrary.add(name, content)
  }
}

export default GerclawRagProvider
