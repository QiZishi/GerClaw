/** Replaceable document parsing seam consumed by GerClaw file upload. */
import { Context, Service } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'

export interface ParsedDocument {
  taskId: string
  markdownPath: string
  elapsedMs: number
  provider: 'MinerU'
}

declare module '@deepseek-ai/cordis' {
  interface Context { gerclawDocumentParser: GerclawDocumentParser }
}

export abstract class GerclawDocumentParser extends Service {
  constructor(ctx: Context) { super(ctx, 'gerclawDocumentParser') }
  abstract parse(agent: Agent, sourcePath: string, name: string, signal: AbortSignal): Promise<ParsedDocument>
}

export default GerclawDocumentParser
