/** Shared immutable medical corpus provider derived from dsh-library 0.1.3. */
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
import { join, relative } from 'node:path'
import { Context, Service } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import {
  GerclawSharedKnowledge,
  type GerclawRagHit as LocalRagHit,
  type GerclawRagStatus as LocalRagStatus,
} from '@gerclaw/library'
import type {
  GerclawLibraryRuntime,
  GerclawLibrarySearchHit,
} from '@gerclaw/library-dsh-runtime'

export interface LocalRagConfig {
  knowledgeBasePath: string
  sharedIndexRoot: string
  library?: string
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

export class SharedKnowledgeProvider extends GerclawSharedKnowledge {
  static inject = ['gerclawLibraryRuntime']
  static Config: z<LocalRagConfig> = z.object({
    knowledgeBasePath: z.string().required(),
    sharedIndexRoot: z.string().required(),
    library: z.string().default('gerclaw-medical'),
    embeddingDimensions: z.number().min(8).default(DEFAULT_EMBEDDING_DIMENSIONS),
    embeddingModel: z.string().default(DEFAULT_EMBEDDING_MODEL),
    rerankApiKey: z.string().required(),
    rerankUrl: z.string().required(),
    rerankModel: z.string().required(),
  })
  private readonly controller = new AbortController()
  private readonly library: string
  private readonly baseSources = new Map<string, SharedSourceRef>()
  private readonly shardRoutes: SharedShardRoute[] = []
  private readonly runtime: GerclawLibraryRuntime
  private current: LocalRagStatus = { state: 'indexing', total: 0, indexed: 0 }
  private ready: Promise<void> = Promise.resolve()

  constructor(ctx: Context, private readonly config: LocalRagConfig) {
    super(ctx)
    this.library = config.library ?? 'gerclaw-medical'
    this.runtime = ctx.gerclawLibraryRuntime
    ctx.effect(() => () => {
      this.controller.abort()
    }, 'gerclaw.local-rag.lifecycle')
  }

  protected async [Service.init](): Promise<void> {
    await mkdir(this.config.sharedIndexRoot, { recursive: true })
    this.ready = this.initialize()
    void this.ready.catch(() => {})
  }

  status(): LocalRagStatus { return { ...this.current } }


  private async buildSharedIndex(manifest: CorpusManifest, versionDir: string): Promise<void> {
    const staging = join(this.config.sharedIndexRoot, `.building-${manifest.version}-${randomUUID()}`)
    await mkdir(staging, { recursive: true })
    try {
      const versionPrefix = `${this.library}-${manifest.version.slice(0, 12)}-`
      for (const entry of this.runtime.list().filter(row => row.library.startsWith(versionPrefix))) {
        this.controller.signal.throwIfAborted()
        await this.runtime.remove(entry.library, entry.documentId)
      }
      const documents = await Promise.all(manifest.files.map(async entry => ({
        path: entry.path,
        content: await readFile(join(this.config.knowledgeBasePath, entry.path), 'utf8'),
      })))
      const shards = planSharedShards(documents)
      const routing: SharedRouting = { version: 1, shards: [], sources: {} }
      let indexed = 0
      const indexedPaths = new Set<string>()
      for (const [shardIndex, shard] of shards.entries()) {
        const library = `${versionPrefix}s${shardIndex.toString(36)}`
        const routeParts = [shard.category]
        for (const [segmentIndex, segment] of shard.segments.entries()) {
          this.controller.signal.throwIfAborted()
          const sourceMarker = `<!-- gerclaw-source: ${segment.path}; segment: ${segment.seqBase} -->\n`
          const added = await this.runtime.add(
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
      const entries = this.runtime.list().filter(entry => entry.library.startsWith(versionPrefix))
      const names = new Set(entries.map(entry => entry.name))
      for (const entry of manifest.files) {
        if (!names.has(entry.path)) throw new Error(`共享知识库索引缺少：${entry.path}`)
      }
      if (routing.shards.length === 0 || Object.keys(routing.sources).length !== entries.length)
        throw new Error('共享知识库分片路由校验失败')
      await writeFile(join(staging, 'manifest.json'), JSON.stringify(manifest))
      await writeFile(join(staging, 'routing.json'), JSON.stringify(routing))
      await writeFile(join(staging, 'READY'), `${manifest.version}\n`)
      if (await exists(versionDir)) await rm(staging, { recursive: true, force: true })
      else await rename(staging, versionDir)
    } catch (error) {
      await rm(staging, { recursive: true, force: true })
      throw error
    }
  }

  private async ensureSharedIndex(manifest: CorpusManifest): Promise<string> {
    const versionDir = join(this.config.sharedIndexRoot, manifest.version)
    const ready = join(versionDir, 'READY')
    if (await exists(ready)) {
      const routing = JSON.parse(await readFile(join(versionDir, 'routing.json'), 'utf8')) as SharedRouting
      const indexed = new Set(this.runtime.list().map(entry => entry.documentId))
      if (!Object.keys(routing.sources).every(documentId => indexed.has(documentId))) {
        await rm(versionDir, { recursive: true, force: true })
      }
    }
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
      const routing = JSON.parse(
        await readFile(join(versionDir, 'routing.json'), 'utf8'),
      ) as SharedRouting
      this.shardRoutes.push(...routing.shards)
      for (const [documentId, source] of Object.entries(routing.sources))
        this.baseSources.set(documentId, source)
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

  private baseHits(hits: readonly GerclawLibrarySearchHit[]): LocalRagHit[] {
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
    const limit = Math.max(topK, 20)
    const selectedRoutes = await this.rerankIndexes(
      query,
      this.shardRoutes.map(route => route.routeText),
      SHARD_ROUTE_LIMIT,
      signal,
    )
    const baseGroups = await Promise.all(selectedRoutes.map(async ({ index }) => {
      const route = this.shardRoutes[index]
      if (route === undefined) throw new Error('共享知识库分片路由无效')
      return this.baseHits(await this.runtime.search(route.library, query, limit, signal))
    }))
    const candidates = baseGroups.flat()
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

}

export default SharedKnowledgeProvider
