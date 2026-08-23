/** GerClaw's copied medical corpus, indexed and retrieved through dsh-library tools. */
import { readFile, readdir } from 'node:fs/promises'
import { join, relative } from 'node:path'
import { Context, Service } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-commands'
import type {} from '@deepseek-ai/dsh-storage-domain'
import type {} from '@deepseek-ai/dsh-subprocess'
import {
  allTools,
  LibraryStore,
  libraryDomainSpec,
  resolveConfig,
} from 'dsh-library'
export interface LocalRagConfig {
  knowledgeBasePath: string
  library?: string
  embeddingCommand?: string
  embeddingDimensions?: number
  rerankApiKey?: string
  rerankUrl?: string
  rerankModel?: string
}
export interface LocalRagHit {
  chunkId: string
  documentId: string
  seq: number
  snippet: string
  score: number
}
export interface LocalRagStatus {
  state: 'indexing' | 'ready' | 'failed'
  total: number
  indexed: number
  error?: string
}
const files = async (root: string): Promise<string[]> => {
  const out: string[] = []
  const walk = async (dir: string) => {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name)
      if (entry.isDirectory()) await walk(path)
      else if (entry.isFile() && /\.(?:md|txt)$/i.test(entry.name))
        out.push(path)
    }
  }
  await walk(root)
  return out.sort()
}
const sourceName = (name: string) => name.replace(/#part-\d+$/, '')
declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawRag: LocalRagService
  }
}
export class LocalRagService extends Service {
  static inject = ['tools', 'commands', 'storageDomain', 'subprocess']
  private readonly controller = new AbortController()
  private readonly library: string
  private store!: LibraryStore
  private documents: Array<{ id: string; text: string }> = []
  private readonly sourceByDocumentId = new Map<string, string>()
  private readonly indexedNames = new Set<string>()
  private readonly indexedSources = new Set<string>()
  private indexQueue: Promise<void> = Promise.resolve()
  private hasUserDocuments = false
  private current: LocalRagStatus = { state: 'indexing', total: 0, indexed: 0 }
  private ready: Promise<void> = Promise.resolve()
  constructor(
    ctx: Context,
    private readonly config: LocalRagConfig,
  ) {
    super(ctx, 'gerclawRag')
    this.library = config.library ?? 'gerclaw-medical'
    ctx.effect(
      () => () => {
        this.controller.abort()
      },
      'gerclaw.local-rag.abort',
    )
  }
  protected async [Service.init](): Promise<void> {
    const resolved = resolveConfig({
      chunkSize: 900,
      chunkOverlap: 120,
      maxFileBytes: 5_242_880,
      embedding: {
        dims: this.config.embeddingDimensions ?? 1024,
        command: this.config.embeddingCommand ?? '',
        timeoutMs: 300_000,
        graceMs: 1_000,
        maxOutputBytes: 67_108_864,
        maxBatchItems: 64,
      },
      search: {
        topK: 8,
        hybridWeight: 0.6,
        minRelevance: 0.15,
        diversityLambda: 0.5,
        lostMiddleHead: 1,
        lostMiddleTail: 1,
        maxResultChars: 16_000,
      },
      injection: { enabled: true, maxChars: 12_000 },
      citation: { windowChars: 150, minScore: 40, minSemantic: 0.1 },
      purge: { signatureLength: 4, maxProbes: 24 },
      diagnose: { maxDuplicatePairs: 24, sampleCap: 200, positionBins: 5 },
    })
    const domain = await this.ctx.storageDomain.open(libraryDomainSpec)
    this.ctx.effect(() => () => domain.close(), 'gerclaw.local-rag.domain')
    this.store = new LibraryStore(domain, resolved, {
      subprocess: this.ctx.subprocess,
    })
    for (const tool of allTools({
      ctx: this.ctx,
      config: resolved,
      store: this.store,
    }))
      this.ctx.effect(
        () => this.ctx.tools.register(tool),
        `gerclaw.local-rag.${tool.name}`,
      )
    this.ready = this.index()
    void this.ready.catch(() => {})
  }
  status(): LocalRagStatus {
    return { ...this.current }
  }
  private async index(): Promise<void> {
    try {
      const all = await files(this.config.knowledgeBasePath)
      this.documents = await Promise.all(
        all.map(async path => ({
          id: relative(this.config.knowledgeBasePath, path),
          text: await readFile(path, 'utf8'),
        })),
      )
      this.current = { state: 'indexing', total: all.length, indexed: 0 }
      const knownEntries = this.store.list(this.library)
      for (const entry of knownEntries) {
        this.sourceByDocumentId.set(entry.documentId, sourceName(entry.name))
        this.indexedNames.add(entry.name)
        this.indexedSources.add(sourceName(entry.name))
      }
      const userEntries = this.store.list('gerclaw-user')
      this.hasUserDocuments = userEntries.length > 0
      for (const entry of userEntries)
        this.sourceByDocumentId.set(entry.documentId, entry.name)
      // The 45 MB corpus is catalogued immediately and embedded on demand.
      // This keeps every account's index independent without making a new
      // account wait for hundreds of unrelated remote embedding requests.
      this.current = {
        state: 'ready',
        total: all.length,
        indexed: this.indexedSources.size,
      }
    } catch (error) {
      if (!this.controller.signal.aborted)
        this.current = {
          ...this.current,
          state: 'failed',
          error: error instanceof Error ? error.message : '本地知识库索引失败',
        }
      throw error
    }
  }
  private async ensureRelevantSources(query: string): Promise<void> {
    const terms = [...new Set(
      query.toLocaleLowerCase().match(/[a-z0-9][a-z0-9-]{1,}|[\p{Script=Han}]{2,}/gu)
        ?? [],
    )]
    if (terms.length === 0) return
    const matches = this.documents.flatMap((document) => {
      const lowerName = document.id.toLocaleLowerCase()
      const lowerText = document.text.toLocaleLowerCase()
      let score = 0
      let first = -1
      for (const term of terms) {
        if (lowerName.includes(term)) score += 40
        const position = lowerText.indexOf(term)
        if (position >= 0) {
          score += 10
          if (first < 0 || position < first) first = position
        }
      }
      if (score === 0) return []
      const start = Math.max(0, first < 0 ? 0 : first - 4_000)
      const aligned = Math.floor(start / 8_000) * 8_000
      return [{
        source: document.id,
        score,
        name: `${document.id}#part-${Math.floor(aligned / 8_000) + 1}`,
        text: document.text.slice(aligned, aligned + 16_000),
      }]
    }).sort((a, b) => b.score - a.score).slice(0, 8)
    if (matches.length === 0) return
    this.indexQueue = this.indexQueue.then(async () => {
      for (const match of matches) {
        this.controller.signal.throwIfAborted()
        if (this.indexedNames.has(match.name)) continue
        const added = await this.store.add(
          this.library,
          match.name,
          match.text,
        )
        this.indexedNames.add(match.name)
        this.indexedSources.add(match.source)
        this.sourceByDocumentId.set(added.documentId, match.source)
      }
      this.current = {
        state: 'ready',
        total: this.documents.length,
        indexed: this.indexedSources.size,
      }
    })
    await this.indexQueue
  }
  async search(query: string, topK: number = 8): Promise<LocalRagHit[]> {
    await this.ready
    await this.ensureRelevantSources(query)
    const limit = Math.max(topK, 20)
    const [base, user] = await Promise.all([
      this.indexedNames.size > 0
        ? this.store.search(this.library, query, limit)
        : Promise.resolve([]),
      this.hasUserDocuments
        ? this.store.search('gerclaw-user', query, limit)
        : Promise.resolve([]),
    ])
    const candidates: LocalRagHit[] = [...base, ...user]
      .sort((a, b) => b.score - a.score)
      .slice(0, limit)
    const missing = [
      ['SILICONFLOW_API_KEY', this.config.rerankApiKey],
      ['SILICONFLOW_URL', this.config.rerankUrl],
      ['RERANK_MODEL', this.config.rerankModel],
    ].filter(([, value]) => !value).map(([name]) => name)
    if (missing.length)
      throw new Error(`缺少环境变量：${missing.join('、')}`)
    if (candidates.length === 0) return []
    const response = await fetch(
      `${this.config.rerankUrl?.replace(/\/$/, '')}/rerank`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${this.config.rerankApiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: this.config.rerankModel,
          query,
          documents: candidates.map(hit => hit.snippet),
          top_n: topK,
          return_documents: false,
        }),
        signal: this.controller.signal,
      },
    )
    if (!response.ok)
      throw new Error(`SiliconFlow rerank 请求失败（${response.status}）`)
    const payload = await response.json() as {
      results?: Array<{ index?: number; relevance_score?: number }>
    }
    const ranked = payload.results ?? []
    if (ranked.length === 0)
      throw new Error('SiliconFlow rerank 没有返回排序结果')
    return ranked.map((row) => {
      const hit = candidates[row.index ?? -1]
      if (!hit) throw new Error('SiliconFlow rerank 返回了无效索引')
      return {
        ...hit,
        documentId:
          this.sourceByDocumentId.get(hit.documentId) ?? hit.documentId,
        score: row.relevance_score ?? hit.score,
      }
    })
  }
  async addUserDocument(path: string, name: string): Promise<unknown> {
    const added = await this.store.add(
      'gerclaw-user',
      name,
      await readFile(path, 'utf8'),
    )
    this.sourceByDocumentId.set(added.documentId, added.name)
    this.hasUserDocuments = true
    return added
  }
}
export default LocalRagService
