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
}

export default GerclawArtifactService
