/** Shared immutable medical corpus plus account-private dsh-library overlay. */
import { createHash, randomUUID } from 'node:crypto'
import {
  mkdir,
  open,
  readFile,
  readdir,
  rename,
  rm,
  stat,
  unlink,
  writeFile,
} from 'node:fs/promises'
import { dirname, join, relative } from 'node:path'
import { Context, Service } from '@deepseek-ai/cordis'
import { CallId } from '@deepseek-ai/dsh-llm'
import { DomainFacility, type Domain, type DomainSpec } from '@deepseek-ai/dsh-storage-domain'
import { SqliteStorageBackend } from '@deepseek-ai/dsh-storage-sqlite'
import type {} from '@deepseek-ai/dsh-storage'
import type {} from '@deepseek-ai/dsh-subprocess'
import type {} from '@deepseek-ai/dsh-tools'

interface LibrarySearchHit {
  readonly chunkId: string
  readonly documentId: string
  readonly seq: number
  readonly snippet: string
  readonly score: number
}

interface LibraryListEntry {
  readonly documentId: string
  readonly name: string
}

interface LibraryStoreLike {
  add(
    library: string,
    docName: string,
    content: string,
  ): Promise<{ documentId: string }>
  list(library?: string): LibraryListEntry[]
  search(library: string, query: string, topK?: number): Promise<LibrarySearchHit[]>
}

interface LibraryRuntime {
  LibraryStore: new (
    domain: Domain<DomainSpec>,
    config: unknown,
    deps: { subprocess: Context['subprocess'] },
  ) => LibraryStoreLike
  libraryDomainSpec: DomainSpec
  resolveConfig: (config: Record<string, unknown>) => unknown
}

const loadLibraryRuntime = async (): Promise<LibraryRuntime> => {
  // Keep dsh-library's package-level SessionEventMap augmentation outside the
  // DSH Typert program. The runtime value is still the unmodified 0.1.3
  // implementation selected by the workspace lockfile.
  const packageName = ['dsh', 'library'].join('-')
  const runtime: unknown = await import(packageName)
  return runtime as LibraryRuntime
}

export interface LocalRagConfig {
  knowledgeBasePath: string
  sharedIndexRoot: string
  library?: string
  embeddingCommand?: string
  embeddingDimensions?: number
  embeddingModel?: string
  rerankApiKey?: string
  rerankUrl?: string
  rerankModel?: string
}

export interface CorpusManifestEntry {
  path: string
  bytes: number
  sha256: string
}

export interface CorpusManifest {
  schemaVersion: 3
  version: string
  index: {
    chunkSize: number
    chunkOverlap: number
    embeddingDimensions: number
    embeddingModel: string
    shardMaxChunks: number
    segmentChars: number
    segmentOverlap: number
  }
  files: CorpusManifestEntry[]
}

export interface LocalRagHit {
  chunkId: string
  documentId: string
  seq: number
  snippet: string
  score: number
  origin: 'knowledge-base' | 'user'
}

export interface LocalRagStatus {
  state: 'indexing' | 'ready' | 'failed'
  total: number
  indexed: number
  version?: string
  error?: string
}

const USER_LIBRARY = 'gerclaw-user'
const LOCK_STALE_MS = 30 * 60_000
const SHARED_CHUNK_SIZE = 4_000
const SHARED_CHUNK_OVERLAP = 400
const SHARD_MAX_CHUNKS = 80
const SHARD_SEGMENT_CHARS = 180_000
const SHARD_SEGMENT_OVERLAP = 4_000
const SHARD_ROUTE_LIMIT = 8
const DEFAULT_EMBEDDING_DIMENSIONS = 1_024
const DEFAULT_EMBEDDING_MODEL = 'BAAI/bge-m3'

const listCorpusFiles = async (root: string): Promise<string[]> => {
  const out: string[] = []
  const walk = async (dir: string): Promise<void> => {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name)
      if (entry.isDirectory()) await walk(path)
      else if (entry.isFile() && /\.md$/iu.test(entry.name)) out.push(path)
    }
  }
  await walk(root)
  return out.sort()
}

export async function createCorpusManifest(
  root: string,
  options: { embeddingDimensions?: number; embeddingModel?: string } = {},
): Promise<CorpusManifest> {
  const paths = await listCorpusFiles(root)
  const files = await Promise.all(paths.map(async (path): Promise<CorpusManifestEntry> => {
    const content = await readFile(path)
    return {
      path: relative(root, path),
      bytes: content.byteLength,
      sha256: createHash('sha256').update(content).digest('hex'),
    }
  }))
  const index = {
    chunkSize: SHARED_CHUNK_SIZE,
    chunkOverlap: SHARED_CHUNK_OVERLAP,
    embeddingDimensions: options.embeddingDimensions ?? DEFAULT_EMBEDDING_DIMENSIONS,
    embeddingModel: options.embeddingModel ?? DEFAULT_EMBEDDING_MODEL,
    shardMaxChunks: SHARD_MAX_CHUNKS,
    segmentChars: SHARD_SEGMENT_CHARS,
    segmentOverlap: SHARD_SEGMENT_OVERLAP,
  }
  const canonical = JSON.stringify({ schemaVersion: 3, index, files })
  return {
    schemaVersion: 3,
    version: createHash('sha256').update(canonical).digest('hex'),
    index,
    files,
  }
}

const exists = async (path: string): Promise<boolean> => {
  try { await stat(path); return true } catch { return false }
}

const delay = (ms: number, signal: AbortSignal) => new Promise<void>((resolve, reject) => {
  const finish = () => {
    signal.removeEventListener('abort', abort)
    resolve()
  }
  const timer = setTimeout(finish, ms)
  const abort = () => {
    clearTimeout(timer)
    signal.removeEventListener('abort', abort)
    reject(new DOMException('共享知识库索引已停止', 'AbortError'))
  }
  signal.addEventListener('abort', abort, { once: true })
})

declare module '@deepseek-ai/cordis' {
  interface Context { gerclawRag: LocalRagService }
}

interface SharedLibraryHandle {
  store: LibraryStoreLike
  close: () => Promise<void>
}

interface SharedSourceRef {
  path: string
  seqBase: number
}

interface SharedShardRoute {
  library: string
  routeText: string
}

interface SharedRouting {
  version: 1
  shards: SharedShardRoute[]
  sources: Record<string, SharedSourceRef>
}

export interface PlannedSegment {
  path: string
  content: string
  seqBase: number
  estimatedChunks: number
  routeExcerpt: string
}

export interface PlannedShard {
  category: string
  segments: PlannedSegment[]
  estimatedChunks: number
}

const compactRouteText = (text: string, max = 240): string => {
  const compact = text.replace(/<!--[\s\S]*?-->/gu, ' ').replace(/\s+/gu, ' ').trim()
  if (compact.length <= max) return compact
  const window = Math.floor(max / 3)
  const middle = Math.floor(compact.length / 2)
  return [
    compact.slice(0, window),
    compact.slice(
      Math.max(0, middle - Math.floor(window / 2)),
      middle + Math.ceil(window / 2),
    ),
    compact.slice(-window),
  ].join(' ')
}

const corpusCategory = (path: string): string => {
  const parts = path.split('/')
  return parts.length > 2 && parts[1] !== undefined
    ? parts[1]
    : '通用医学资料'
}

export const planSharedShards = (
  documents: readonly { path: string; content: string }[],
): PlannedShard[] => {
  const byCategory = new Map<string, PlannedSegment[]>()
  for (const document of documents) {
    const category = corpusCategory(document.path)
    const segments = byCategory.get(category) ?? []
    let start = 0
    let segmentIndex = 0
    while (start < document.content.length || (start === 0 && document.content.length === 0)) {
      const end = Math.min(document.content.length, start + SHARD_SEGMENT_CHARS)
      const content = document.content.slice(start, end)
      segments.push({
        path: document.path,
        content,
        seqBase: segmentIndex * 1_000,
        estimatedChunks: Math.max(1, Math.ceil(content.length / (SHARED_CHUNK_SIZE - SHARED_CHUNK_OVERLAP))),
        routeExcerpt: compactRouteText(content),
      })
      if (end >= document.content.length) break
      start = end - SHARD_SEGMENT_OVERLAP
      segmentIndex += 1
    }
    byCategory.set(category, segments)
  }
  const planned: PlannedShard[] = []
  for (const [category, segments] of [...byCategory].sort(([a], [b]) => a.localeCompare(b))) {
    let current: PlannedShard | undefined
    for (const segment of segments) {
      if (current === undefined
        || current.estimatedChunks + segment.estimatedChunks > SHARD_MAX_CHUNKS) {
        current = { category, segments: [], estimatedChunks: 0 }
        planned.push(current)
      }
      current.segments.push(segment)
      current.estimatedChunks += segment.estimatedChunks
    }
  }
  return planned
}

export class LocalRagService extends Service {
  static inject = ['tools', 'storage', 'subprocess']
  private readonly controller = new AbortController()
  private readonly library: string
  private readonly stagingDir: string
  private readonly baseSources = new Map<string, SharedSourceRef>()
  private readonly shardRoutes: SharedShardRoute[] = []
  private readonly userSources = new Map<string, string>()
  private runtime!: LibraryRuntime
  private shared: SharedLibraryHandle | undefined
  private hasUserDocuments = false
  private current: LocalRagStatus = { state: 'indexing', total: 0, indexed: 0 }
  private ready: Promise<void> = Promise.resolve()

  constructor(ctx: Context, private readonly config: LocalRagConfig) {
    super(ctx, 'gerclawRag')
    this.library = config.library ?? 'gerclaw-medical'
    this.stagingDir = join(dirname(config.knowledgeBasePath), 'workspace', '.gerclaw-rag')
    ctx.effect(() => async () => {
      this.controller.abort()
      await this.shared?.close()
      this.shared = undefined
    }, 'gerclaw.local-rag.lifecycle')
  }

  protected async [Service.init](): Promise<void> {
    await mkdir(this.stagingDir, { recursive: true })
    await mkdir(this.config.sharedIndexRoot, { recursive: true })
    this.runtime = await loadLibraryRuntime()
    await this.waitForLibraryTools()
    this.ready = this.initialize()
    void this.ready.catch(() => {})
  }

  status(): LocalRagStatus { return { ...this.current } }

  private async waitForLibraryTools(): Promise<void> {
    const deadline = Date.now() + 10_000
    while (Date.now() < deadline) {
      this.controller.signal.throwIfAborted()
      if (this.ctx.tools.get('library_add') && this.ctx.tools.get('library_list') && this.ctx.tools.get('library_search')) return
      await delay(25, this.controller.signal)
    }
    throw new Error('dsh-library 工具未能完成加载')
  }

  private async runLibraryTool<T>(
    name: 'library_add' | 'library_list' | 'library_search',
    args: Record<string, unknown>,
    signal?: AbortSignal,
  ): Promise<T> {
    const result = await this.ctx.tools.execute({
      callId: CallId(`gerclaw-rag-${randomUUID()}`),
      name,
      arguments: args,
      signal: this.requestSignal(signal),
    })
    if (result.isError) {
      const message = result.content.filter(block => block.type === 'text').map(block => block.text).join('\n')
      throw new Error(message || `${name} 执行失败`)
    }
    return result.value as T
  }

  private libraryConfig() {
    return this.runtime.resolveConfig({
      chunkSize: SHARED_CHUNK_SIZE,
      chunkOverlap: SHARED_CHUNK_OVERLAP,
      maxFileBytes: 5 * 1024 * 1024,
      embedding: {
        dims: this.config.embeddingDimensions ?? DEFAULT_EMBEDDING_DIMENSIONS,
        ...(this.config.embeddingCommand ? { command: this.config.embeddingCommand } : {}),
        timeoutMs: 120_000,
        graceMs: 2_000,
        maxOutputBytes: 64 * 1024 * 1024,
        maxBatchItems: 64,
      },
      search: {
        topK: 20,
        hybridWeight: 0.7,
        // dsh-library 0.1.3 treats one contiguous CJK phrase as one lexical
        // token. The account-local SiliconFlow reranker owns the final gate.
        minRelevance: 0,
        diversityLambda: 0.55,
        lostMiddleHead: 2,
        lostMiddleTail: 1,
        maxResultChars: 40_000,
      },
      injection: { enabled: false, maxChars: 12_000 },
    })
  }

  private async openSharedStore(databasePath: string): Promise<SharedLibraryHandle> {
    await mkdir(dirname(databasePath), { recursive: true })
    const backend = new SqliteStorageBackend({ path: databasePath, journalMode: 'wal' })
    const backendName = `gerclaw-shared-rag-${randomUUID()}`
    const unregister = this.ctx.storage.backend.register(backendName, backend)
    const facility = new DomainFacility(this.ctx, { backend: backendName })
    try {
      const domain = await facility.open(this.runtime.libraryDomainSpec)
      const store = new this.runtime.LibraryStore(domain, this.libraryConfig(), { subprocess: this.ctx.subprocess })
      let closed = false
      return {
        store,
        close: async () => {
          if (closed) return
          closed = true
          await domain.close()
          await facility.closeAll()
          unregister()
          await backend.close()
        },
      }
    } catch (error) {
      unregister()
      await backend.close()
      throw error
    }
  }

  private async buildSharedIndex(manifest: CorpusManifest, versionDir: string): Promise<void> {
    const staging = join(this.config.sharedIndexRoot, `.building-${manifest.version}-${randomUUID()}`)
    await mkdir(staging, { recursive: true })
    let handle: SharedLibraryHandle | undefined
    try {
      handle = await this.openSharedStore(join(staging, 'index.sqlite'))
      const documents = await Promise.all(manifest.files.map(async entry => ({
        path: entry.path,
        content: await readFile(join(this.config.knowledgeBasePath, entry.path), 'utf8'),
      })))
      const shards = planSharedShards(documents)
      const routing: SharedRouting = { version: 1, shards: [], sources: {} }
      let indexed = 0
      const indexedPaths = new Set<string>()
      for (const [shardIndex, shard] of shards.entries()) {
        const library = `${this.library}-s${shardIndex.toString(36)}`
        const routeParts = [shard.category]
        for (const [segmentIndex, segment] of shard.segments.entries()) {
          this.controller.signal.throwIfAborted()
          const sourceMarker = `<!-- gerclaw-source: ${segment.path}; segment: ${segment.seqBase} -->\n`
          const added = await handle.store.add(
            library,
            segment.path,
            `${sourceMarker}${segment.content}`,
          )
          routing.sources[added.documentId] = {
            path: segment.path,
            seqBase: segment.seqBase,
          }
          routeParts.push(`${segment.path} ${segment.routeExcerpt}`)
          if (!indexedPaths.has(segment.path)) {
            indexedPaths.add(segment.path)
            indexed += 1
            this.current = {
              state: 'indexing',
              total: manifest.files.length,
              indexed,
              version: manifest.version,
            }
          }
          if (segmentIndex % 8 === 0) await delay(0, this.controller.signal)
        }
        routing.shards.push({
          library,
          routeText: routeParts.join('\n').slice(0, 4_000),
        })
      }
      const entries = handle.store.list()
      const names = new Set(entries.map(entry => entry.name))
      for (const entry of manifest.files) {
        if (!names.has(entry.path)) throw new Error(`共享知识库索引缺少：${entry.path}`)
      }
      if (routing.shards.length === 0 || Object.keys(routing.sources).length !== entries.length)
        throw new Error('共享知识库分片路由校验失败')
      await handle.close()
      handle = undefined
      await writeFile(join(staging, 'manifest.json'), JSON.stringify(manifest))
      await writeFile(join(staging, 'routing.json'), JSON.stringify(routing))
      await writeFile(join(staging, 'READY'), `${manifest.version}\n`)
      if (await exists(versionDir)) await rm(staging, { recursive: true, force: true })
      else await rename(staging, versionDir)
    } catch (error) {
      await handle?.close().catch(() => {})
      await rm(staging, { recursive: true, force: true })
      throw error
    }
  }

  private async ensureSharedIndex(manifest: CorpusManifest): Promise<string> {
    const versionDir = join(this.config.sharedIndexRoot, manifest.version)
    const ready = join(versionDir, 'READY')
    if (!(await exists(ready))) {
      const lockPath = join(this.config.sharedIndexRoot, `${manifest.version}.lock`)
      let lock: Awaited<ReturnType<typeof open>> | undefined
      try {
        lock = await open(lockPath, 'wx', 0o600)
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error
        const lockStat = await stat(lockPath).catch(() => undefined)
        if (lockStat && Date.now() - lockStat.mtimeMs > LOCK_STALE_MS) {
          await unlink(lockPath).catch(() => {})
          return this.ensureSharedIndex(manifest)
        }
        while (await exists(lockPath)) {
          this.controller.signal.throwIfAborted()
          await delay(250, this.controller.signal)
        }
        if (!(await exists(ready))) return this.ensureSharedIndex(manifest)
      }
      if (lock) {
        try { await this.buildSharedIndex(manifest, versionDir) }
        finally {
          await lock.close()
          await unlink(lockPath).catch(() => {})
        }
      }
    }
    const stored = JSON.parse(await readFile(join(versionDir, 'manifest.json'), 'utf8')) as CorpusManifest
    const routing = JSON.parse(await readFile(join(versionDir, 'routing.json'), 'utf8')) as SharedRouting
    if (stored.version !== manifest.version
      || stored.files.length !== manifest.files.length
      || routing.shards.length === 0)
      throw new Error('共享知识库索引清单与当前 437 份资料不一致')
    const pointer = join(this.config.sharedIndexRoot, 'current.json')
    const temp = `${pointer}.${process.pid}.${randomUUID()}.tmp`
    await writeFile(temp, JSON.stringify({ version: manifest.version, updatedAt: new Date().toISOString() }), { mode: 0o600 })
    await rename(temp, pointer)
    return versionDir
  }

  private async initialize(): Promise<void> {
    try {
      const manifest = await createCorpusManifest(this.config.knowledgeBasePath, {
        ...(this.config.embeddingDimensions === undefined
          ? {}
          : { embeddingDimensions: this.config.embeddingDimensions }),
        ...(this.config.embeddingModel === undefined
          ? {}
          : { embeddingModel: this.config.embeddingModel }),
      })
      this.current = { state: 'indexing', total: manifest.files.length, indexed: 0, version: manifest.version }
      const versionDir = await this.ensureSharedIndex(manifest)
      this.shared = await this.openSharedStore(join(versionDir, 'index.sqlite'))
      const routing = JSON.parse(
        await readFile(join(versionDir, 'routing.json'), 'utf8'),
      ) as SharedRouting
      this.shardRoutes.push(...routing.shards)
      for (const [documentId, source] of Object.entries(routing.sources))
        this.baseSources.set(documentId, source)
      const userEntries = await this.runLibraryTool<{ entries: Array<{ documentId: string; name: string }> }>('library_list', { library: USER_LIBRARY })
      this.hasUserDocuments = userEntries.entries.length > 0
      for (const entry of userEntries.entries) this.userSources.set(entry.documentId, entry.name)
      this.current = {
        state: 'ready',
        total: manifest.files.length,
        indexed: manifest.files.length,
        version: manifest.version,
      }
    } catch (error) {
      if (!this.controller.signal.aborted) {
        this.current = {
          ...this.current,
          state: 'failed',
          error: error instanceof Error ? error.message : '共享知识库索引失败',
        }
      }
      throw error
    }
  }

  private baseHits(hits: readonly LibrarySearchHit[]): LocalRagHit[] {
    return hits.map((hit) => {
      const source = this.baseSources.get(hit.documentId)
      return {
        ...hit,
        documentId: source?.path ?? hit.documentId,
        seq: (source?.seqBase ?? 0) + hit.seq,
        origin: 'knowledge-base',
      }
    })
  }

  private async userHits(
    query: string,
    topK: number,
    signal?: AbortSignal,
  ): Promise<LocalRagHit[]> {
    if (!this.hasUserDocuments) return []
    const result = await this.runLibraryTool<{ results: LibrarySearchHit[] }>('library_search', {
      library: USER_LIBRARY, query, topK, inject: false,
    }, signal)
    return result.results.map(hit => ({
      ...hit,
      documentId: this.userSources.get(hit.documentId) ?? hit.documentId,
      origin: 'user',
    }))
  }

  private requestSignal(signal?: AbortSignal): AbortSignal {
    return signal === undefined
      ? this.controller.signal
      : AbortSignal.any([this.controller.signal, signal])
  }

  private async rerankIndexes(
    query: string,
    documents: readonly string[],
    topN: number,
    signal?: AbortSignal,
  ): Promise<Array<{ index: number; score: number }>> {
    const missing = [
      ['SILICONFLOW_API_KEY', this.config.rerankApiKey],
      ['SILICONFLOW_URL', this.config.rerankUrl],
      ['RERANK_MODEL', this.config.rerankModel],
    ].filter(([, value]) => !value).map(([name]) => name)
    if (missing.length) throw new Error(`缺少环境变量：${missing.join('、')}`)
    if (documents.length === 0) return []
    const response = await fetch(`${this.config.rerankUrl?.replace(/\/$/u, '')}/rerank`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.config.rerankApiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: this.config.rerankModel,
        query,
        documents,
        top_n: Math.min(topN, documents.length),
        return_documents: false,
      }),
      signal: this.requestSignal(signal),
    })
    if (!response.ok) throw new Error(`SiliconFlow rerank 请求失败（${response.status}）`)
    const payload = await response.json() as {
      results?: Array<{ index?: number; relevance_score?: number }>
    }
    if (!payload.results?.length) throw new Error('SiliconFlow rerank 没有返回排序结果')
    return payload.results.map((row) => {
      const index = row.index ?? -1
      if (index < 0 || index >= documents.length)
        throw new Error('SiliconFlow rerank 返回了无效索引')
      return { index, score: row.relevance_score ?? 0 }
    })
  }

  async search(
    query: string,
    topK = 8,
    signal?: AbortSignal,
  ): Promise<LocalRagHit[]> {
    signal?.throwIfAborted()
    if (signal === undefined) {
      await this.ready
    } else {
      await new Promise<void>((resolve, reject) => {
        const aborted = () => {
          reject(signal.reason instanceof Error
            ? signal.reason
            : new DOMException('检索已取消', 'AbortError'))
        }
        signal.addEventListener('abort', aborted, { once: true })
        this.ready.then(resolve, reject).finally(() => {
          signal.removeEventListener('abort', aborted)
        }).catch(() => {})
      })
    }
    signal?.throwIfAborted()
    const shared = this.shared
    if (!shared) throw new Error('共享知识库索引尚未就绪')
    const limit = Math.max(topK, 20)
    const selectedRoutes = await this.rerankIndexes(
      query,
      this.shardRoutes.map(route => route.routeText),
      SHARD_ROUTE_LIMIT,
      signal,
    )
    const [baseGroups, user] = await Promise.all([
      Promise.all(selectedRoutes.map(async ({ index }) => {
        const route = this.shardRoutes[index]
        if (route === undefined) throw new Error('共享知识库分片路由无效')
        return this.baseHits(await shared.store.search(route.library, query, limit))
      })),
      this.userHits(query, limit, signal),
    ])
    const candidates = [...baseGroups.flat(), ...user]
      .sort((a, b) => b.score - a.score)
      .slice(0, limit * SHARD_ROUTE_LIMIT)
    if (candidates.length === 0) return []
    const ranked = await this.rerankIndexes(
      query,
      candidates.map(hit => hit.snippet),
      topK,
      signal,
    )
    return ranked.map((row) => {
      const hit = candidates[row.index]
      if (hit === undefined) throw new Error('SiliconFlow rerank 返回了无效索引')
      return { ...hit, score: row.score }
    })
  }

  async addUserDocument(path: string, name: string): Promise<unknown> {
    const text = await readFile(path, 'utf8')
    const digest = createHash('sha256').update(`${name}\0${text}`).digest('hex')
    const staged = join(this.stagingDir, `${digest}.md`)
    await writeFile(staged, text, { flag: 'w' })
    const added = await this.runLibraryTool<{ documentId: string; name: string }>('library_add', {
      path: staged, library: USER_LIBRARY, name,
    })
    this.userSources.set(added.documentId, added.name)
    this.hasUserDocuments = true
    return added
  }
}

export default LocalRagService
