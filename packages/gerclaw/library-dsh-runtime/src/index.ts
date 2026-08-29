/** Cordis service seam around the dsh-library 0.1.3 storage/search kernel. */
import { Context, Service } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-subprocess'
import z from '@deepseek-ai/schemastery'
import {
  LibraryStore,
  libraryDomainSpec,
  resolveConfig,
  type LibraryAddResult,
  type LibraryListEntry,
  type LibraryRemoveResult,
  type LibrarySearchHit,
  type ResolvedConfig,
} from 'dsh-library'

export interface Config {
  chunkSize?: number
  chunkOverlap?: number
  embeddingCommand?: string
  embeddingDimensions?: number
}

export type GerclawLibraryAddResult = LibraryAddResult
export type GerclawLibraryListEntry = LibraryListEntry
export type GerclawLibraryRemoveResult = LibraryRemoveResult
export type GerclawLibrarySearchHit = LibrarySearchHit

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawLibraryRuntime: GerclawLibraryRuntime
  }
}

/**
 * Replaceable runtime for one isolated dsh-library storage domain.
 * Consumers never import LibraryStore or open its domain themselves.
 */
export abstract class GerclawLibraryRuntime extends Service {
  constructor(ctx: Context) { super(ctx, 'gerclawLibraryRuntime') }

  abstract add(library: string, name: string, content: string): Promise<GerclawLibraryAddResult>
  abstract remove(library: string, documentId: string): Promise<GerclawLibraryRemoveResult>
  abstract list(library?: string): GerclawLibraryListEntry[]
  abstract search(library: string, query: string, topK?: number, signal?: AbortSignal): Promise<GerclawLibrarySearchHit[]>
}

/** Default DSH provider. The only package allowed to construct LibraryStore. */
export class DshLibraryRuntimeProvider extends GerclawLibraryRuntime {
  static inject = ['storageDomain', 'subprocess']
  static Config: z<Config> = z.object({
    chunkSize: z.number().min(100).max(4000).default(900),
    chunkOverlap: z.number().min(0).default(120),
    embeddingCommand: z.string().default(''),
    embeddingDimensions: z.number().min(8).default(1024),
  })

  private readonly libraryConfig: ResolvedConfig
  private store: LibraryStore | undefined

  constructor(ctx: Context, config: Config) {
    super(ctx)
    const chunkSize = config.chunkSize ?? 900
    const chunkOverlap = config.chunkOverlap ?? 120
    if (chunkOverlap >= chunkSize) throw new Error('chunkOverlap 必须小于 chunkSize')
    this.libraryConfig = resolveConfig({
      chunkSize,
      chunkOverlap,
      maxFileBytes: 5 * 1024 * 1024,
      embedding: {
        dims: config.embeddingDimensions ?? 1024,
        command: config.embeddingCommand ?? '',
        timeoutMs: 300_000,
        graceMs: 1_000,
        maxOutputBytes: 64 * 1024 * 1024,
        maxBatchItems: 64,
      },
      search: {
        topK: 20,
        hybridWeight: 0.7,
        minRelevance: 0,
        diversityLambda: 0.55,
        lostMiddleHead: 2,
        lostMiddleTail: 1,
        maxResultChars: 40_000,
      },
      injection: { enabled: false, maxChars: 12_000 },
    })
  }

  protected async [Service.init](): Promise<void> {
    const domain = await this.ctx.storageDomain.open(libraryDomainSpec)
    this.ctx.effect(() => async () => {
      this.store = undefined
      await domain.close()
    }, 'gerclaw.library-dsh-runtime.domain')
    this.store = new LibraryStore(domain, this.libraryConfig, { subprocess: this.ctx.subprocess })
  }

  private ready(): LibraryStore {
    if (this.store === undefined) throw new Error('资料库运行时尚未就绪')
    return this.store
  }

  add(library: string, name: string, content: string): Promise<GerclawLibraryAddResult> {
    return this.ready().add(library, name, content)
  }

  remove(library: string, documentId: string): Promise<GerclawLibraryRemoveResult> {
    return this.ready().remove(library, documentId)
  }

  list(library?: string): GerclawLibraryListEntry[] {
    return this.ready().list(library)
  }

  async search(
    library: string,
    query: string,
    topK = 20,
    signal?: AbortSignal,
  ): Promise<GerclawLibrarySearchHit[]> {
    signal?.throwIfAborted()
    const result = await this.ready().search(library, query, topK)
    signal?.throwIfAborted()
    return result
  }
}

export default DshLibraryRuntimeProvider
