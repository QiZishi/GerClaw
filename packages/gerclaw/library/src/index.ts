/** Replaceable GerClaw private-library, shared-knowledge and RAG service definitions. */
import { Context, Service } from '@deepseek-ai/cordis'

export interface GerclawLibraryDocument {
  documentId: string
  name: string
  chunks: number
  chars: number
  createdAt: number
}

export interface GerclawLibraryHit {
  chunkId: string
  documentId: string
  seq: number
  snippet: string
  score: number
}

export interface GerclawRagHit extends GerclawLibraryHit {
  origin: 'knowledge-base' | 'user'
}

export interface GerclawRagStatus {
  state: 'indexing' | 'ready' | 'failed'
  total: number
  indexed: number
  version?: string
  error?: string
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawLibrary: GerclawLibrary
    gerclawSharedKnowledge: GerclawSharedKnowledge
    gerclawRag: GerclawRag
  }
}

/** Account-private document library. The provider owns its storage-domain handle. */
export abstract class GerclawLibrary extends Service {
  constructor(ctx: Context) { super(ctx, 'gerclawLibrary') }
  abstract add(name: string, content: string): Promise<GerclawLibraryDocument>
  abstract list(): GerclawLibraryDocument[]
  abstract search(query: string, topK?: number, signal?: AbortSignal): Promise<GerclawLibraryHit[]>
}

/** Read-only, content-addressed shared medical corpus. */
export abstract class GerclawSharedKnowledge extends Service {
  constructor(ctx: Context) { super(ctx, 'gerclawSharedKnowledge') }
  abstract status(): GerclawRagStatus
  abstract search(query: string, topK?: number, signal?: AbortSignal): Promise<GerclawRagHit[]>
}

/** Product-facing retrieval service combining shared and account-private results. */
export abstract class GerclawRag extends Service {
  constructor(ctx: Context) { super(ctx, 'gerclawRag') }
  abstract status(): GerclawRagStatus
  abstract search(query: string, topK?: number, signal?: AbortSignal): Promise<GerclawRagHit[]>
  abstract addUserDocument(path: string, name: string): Promise<GerclawLibraryDocument>
}
