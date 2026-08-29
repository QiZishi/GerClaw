/** Replaceable account-scoped artifact service definition. */
import { Context, Service } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'

export type ArtifactFormat = 'md' | 'html' | 'docx' | 'pdf' | 'png' | 'jpg' | 'json'

export interface ArtifactDescriptor {
  artifactId: string
  taskId: string
  sessionId?: string
  name: string
  workspaceRef: string
  format: ArtifactFormat
  mediaType: string
  size: number
  createdAt: string
}

export interface ArtifactSource {
  taskId: string
  sessionId?: string
  kind: string
  result: unknown
}

export interface ArtifactFile {
  descriptor: ArtifactDescriptor
  content: Uint8Array
}

/** A document owned by one exact Agent/session. `sourcePath` is provider-internal
 * and is only used to hand the same workspace file to a parser provider. */
export interface DocumentDescriptor {
  documentId: string
  name: string
  size: number
  createdAt: string
  workspaceRef: string
  parseStatus: 'ready' | 'pending' | 'failed'
  parsedRef?: string
}

export interface StoredDocument {
  descriptor: DocumentDescriptor
  /** Provider-owned workspace path; never serialize this into a client response. */
  sourcePath: string
}

export interface DocumentFile {
  descriptor: DocumentDescriptor
  content: Uint8Array
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawArtifacts: GerclawArtifactService
  }
}

/** Produces and resolves files inside the current account's native Workspace. */
export abstract class GerclawArtifactService extends Service {
  constructor(ctx: Context) { super(ctx, 'gerclawArtifacts') }
  abstract export(agent: Agent, source: ArtifactSource, formats: ArtifactFormat[]): Promise<ArtifactDescriptor[]>
  abstract list(agent?: Agent): ArtifactDescriptor[]
  /** Reads an artifact inside the current account Host boundary. */
  abstract read(artifactId: string): Promise<ArtifactFile | undefined>
  /** Stores an uploaded document inside the exact Agent workspace. */
  abstract storeDocument(agent: Agent, name: string, content: Uint8Array): Promise<StoredDocument>
  /** Updates parser metadata without changing document ownership. */
  abstract updateDocument(agent: Agent, documentId: string, patch: Pick<DocumentDescriptor, 'parseStatus' | 'parsedRef'>): Promise<DocumentDescriptor>
  /** Lists documents owned by the exact Agent/session. */
  abstract listDocuments(agent?: Agent): DocumentDescriptor[]
  /** Reads an uploaded document through the DSH filesystem seam. */
  abstract readDocument(documentId: string): Promise<DocumentFile | undefined>
  /** Reads parsed text through the DSH filesystem seam. */
  abstract readDocumentText(agent: Agent, documentId: string): Promise<string>
}

export default GerclawArtifactService
