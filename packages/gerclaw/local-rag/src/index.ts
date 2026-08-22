/** GerClaw's copied medical corpus, indexed and retrieved through dsh-library tools. */
import { readFile, readdir } from 'node:fs/promises'
import { join, relative } from 'node:path'
import { Context, Service } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-commands'
import type {} from '@deepseek-ai/dsh-storage-domain'
import {
  allTools,
  LibraryStore,
  libraryDomainSpec,
  resolveConfig,
  scoreRelevance,
} from 'dsh-library'
export interface LocalRagConfig {
  knowledgeBasePath: string
  library?: string
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
declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawRag: LocalRagService
  }
}
export class LocalRagService extends Service {
  static inject = ['tools', 'commands', 'storageDomain']
  private readonly controller = new AbortController()
  private readonly library: string
  private store!: LibraryStore
  private documents: Array<{ id: string; text: string }> = []
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
        dims: 256,
        command: '',
        timeoutMs: 30_000,
        graceMs: 1_000,
        maxOutputBytes: 1_048_576,
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
    this.store = new LibraryStore(domain, resolved, { subprocess: undefined })
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
      const known = new Set(
        this.store.list(this.library).map(entry => entry.name),
      )
      let indexed = known.size
      const pending = all.filter(
        path => !known.has(relative(this.config.knowledgeBasePath, path)),
      )
      for (const path of pending) {
        this.controller.signal.throwIfAborted()
        const content = this.documents.find(
          document =>
            document.id === relative(this.config.knowledgeBasePath, path),
        )?.text
        if (content === undefined) throw new Error('知识库文件读取失败')
        await this.store.add(
          this.library,
          relative(this.config.knowledgeBasePath, path),
          content,
        )
        indexed += 1
        this.current = { state: 'indexing', total: all.length, indexed }
      }
      this.current = { state: 'ready', total: all.length, indexed: all.length }
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
  async search(query: string, topK: number = 8): Promise<LocalRagHit[]> {
    while (this.current.state === 'indexing' && this.current.indexed === 0) {
      this.controller.signal.throwIfAborted()
      await new Promise(resolve => setTimeout(resolve, 100))
    }
    if (this.current.state === 'failed') {
      await this.ready
    }
    const baseTerms = query
      .split(/[\s，。；、]+/)
      .map(term => term.trim())
      .filter(Boolean)
    const terms = [
      ...baseTerms,
      ...baseTerms.flatMap(term =>
        /[\u3400-\u9fff]/u.test(term) && term.length > 2
          ? Array.from({ length: term.length - 1 }, (_, index) =>
            term.slice(index, index + 2),
          )
          : [],
      ),
    ]
    return this.documents
      .map((document) => {
        const corpus = `${document.id}\n${document.text}`
        const keywordScore = terms.reduce(
          (sum, term) => sum + (corpus.includes(term) ? 1 : 0),
          0,
        )
        const score = scoreRelevance(query, corpus) + keywordScore
        const positions = terms
          .map(term => document.text.indexOf(term))
          .filter(position => position >= 0)
        const firstPosition =
          positions.length === 0 ? 0 : Math.min(...positions)
        const start = Math.max(0, firstPosition - 180)
        return {
          chunkId: `${document.id}:0`,
          documentId: document.id,
          seq: 0,
          snippet: document.text.slice(start, start + 1_200),
          score,
        }
      })
      .filter(hit => hit.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, topK)
  }
  async addUserDocument(path: string, name: string): Promise<unknown> {
    return this.store.add('gerclaw-user', name, await readFile(path, 'utf8'))
  }
}
export default LocalRagService
