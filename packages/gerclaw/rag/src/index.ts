/** Product RAG consumer: shared medical corpus + account-private library. */
import { readFile } from 'node:fs/promises'
import { Context } from '@deepseek-ai/cordis'
import {
  GerclawRag,
  type GerclawLibraryDocument,
  type GerclawLibraryHit,
  type GerclawRagHit,
  type GerclawRagStatus,
} from '@gerclaw/library'

export class GerclawRagProvider extends GerclawRag {
  static inject = ['gerclawLibrary', 'gerclawSharedKnowledge']

  private readonly controller = new AbortController()

  constructor(ctx: Context) {
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
    return [...shared, ...user].sort((left, right) => right.score - left.score).slice(0, topK)
  }

  async addUserDocument(path: string, name: string): Promise<GerclawLibraryDocument> {
    const content = await readFile(path, 'utf8')
    return this.ctx.gerclawLibrary.add(name, content)
  }
}

export default GerclawRagProvider
