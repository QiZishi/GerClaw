/** Account-private GerClaw library provider derived from dsh-library 0.1.3. */
import { Context, Service } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-subprocess'
import z from '@deepseek-ai/schemastery'
import {
  LibraryStore,
  libraryDomainSpec,
  resolveConfig,
  type LibraryListEntry,
  type ResolvedConfig,
} from 'dsh-library'
import {
  GerclawLibrary,
  type GerclawLibraryDocument,
  type GerclawLibraryHit,
} from '@gerclaw/library'

export interface Config {
  library?: string
  chunkSize?: number
  chunkOverlap?: number
  embeddingCommand?: string
  embeddingDimensions?: number
}

const USER_LIBRARY = 'gerclaw-user'

/** dsh-library's storage algorithm behind a replaceable Cordis service. */
export class DshLibraryProvider extends GerclawLibrary {
  static inject = ['storageDomain', 'subprocess']
  static Config: z<Config> = z.object({
    library: z.string().default(USER_LIBRARY),
    chunkSize: z.number().min(100).max(4000).default(900),
    chunkOverlap: z.number().min(0).default(120),
    embeddingCommand: z.string().default(''),
    embeddingDimensions: z.number().min(8).default(1024),
  })

  private store: LibraryStore | undefined
  private readonly library: string
  private readonly libraryConfig: ResolvedConfig

  constructor(ctx: Context, config: Config) {
    super(ctx)
    this.library = config.library ?? USER_LIBRARY
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
    this.store = new LibraryStore(domain, this.libraryConfig, { subprocess: this.ctx.subprocess })
    this.ctx.effect(() => async () => {
      this.store = undefined
      await domain.close()
    }, 'gerclaw.library-dsh.domain')
  }

  private ready(): LibraryStore {
    if (!this.store) throw new Error('账号资料库尚未就绪')
    return this.store
  }

  async add(name: string, content: string): Promise<GerclawLibraryDocument> {
    const result = await this.ready().add(this.library, name, content)
    const found = this.ready().list(this.library).find(row => row.documentId === result.documentId)
    return found ? this.document(found) : {
      documentId: result.documentId,
      name: result.name,
      chunks: result.chunks,
      chars: result.chars,
      createdAt: Date.now(),
    }
  }

  list(): GerclawLibraryDocument[] {
    return this.ready().list(this.library).map(row => this.document(row))
  }

  async search(query: string, topK = 20, signal?: AbortSignal): Promise<GerclawLibraryHit[]> {
    signal?.throwIfAborted()
    const hits = await this.ready().search(this.library, query, topK)
    signal?.throwIfAborted()
    return hits
  }

  private document(row: LibraryListEntry): GerclawLibraryDocument {
    return {
      documentId: row.documentId,
      name: row.name,
      chunks: row.chunks,
      chars: row.chars,
      createdAt: row.createdAt,
    }
  }
}

export default DshLibraryProvider
