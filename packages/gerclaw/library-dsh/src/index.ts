/** Account-private GerClaw library provider derived from dsh-library 0.1.3. */
import { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import {
  GerclawLibrary,
  type GerclawLibraryDocument,
  type GerclawLibraryHit,
} from '@gerclaw/library'
import type { GerclawLibraryListEntry, GerclawLibraryRuntime } from '@gerclaw/library-dsh-runtime'

export interface Config {
  library?: string
}

const USER_LIBRARY = 'gerclaw-user'

/** dsh-library's storage algorithm behind a replaceable Cordis service. */
export class DshLibraryProvider extends GerclawLibrary {
  static inject = ['gerclawLibraryRuntime']
  static Config: z<Config> = z.object({
    library: z.string().default(USER_LIBRARY),
  })

  private readonly library: string

  constructor(ctx: Context, config: Config) {
    super(ctx)
    this.library = config.library ?? USER_LIBRARY
  }

  async add(name: string, content: string): Promise<GerclawLibraryDocument> {
    const runtime: GerclawLibraryRuntime = this.ctx.gerclawLibraryRuntime
    const result = await runtime.add(this.library, name, content)
    const found = runtime.list(this.library).find(row => row.documentId === result.documentId)
    return found ? this.document(found) : {
      documentId: result.documentId,
      name: result.name,
      chunks: result.chunks,
      chars: result.chars,
      createdAt: Date.now(),
    }
  }

  list(): GerclawLibraryDocument[] {
    return this.ctx.gerclawLibraryRuntime.list(this.library).map(row => this.document(row))
  }

  async search(query: string, topK = 20, signal?: AbortSignal): Promise<GerclawLibraryHit[]> {
    signal?.throwIfAborted()
    const hits = await this.ctx.gerclawLibraryRuntime.search(this.library, query, topK, signal)
    signal?.throwIfAborted()
    return hits
  }

  private document(row: GerclawLibraryListEntry): GerclawLibraryDocument {
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
