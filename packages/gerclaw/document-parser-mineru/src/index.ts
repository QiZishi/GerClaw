/** MinerU provider derived from dsh-mineru 0.1.9 without its Tool or UI surfaces. */
import { randomUUID } from 'node:crypto'
import { createRequire } from 'node:module'
import { dirname, join, resolve, sep } from 'node:path'
import { pathToFileURL } from 'node:url'
import { mkdir, readFile, rm } from 'node:fs/promises'
import { Service } from '@deepseek-ai/cordis'
import type { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import { credentialRef } from '@deepseek-ai/dsh-credentials'
import z from '@deepseek-ai/schemastery'
import { GerclawDocumentParser, type ParsedDocument } from '@gerclaw/document-parser'

export interface Config {
  apiBaseUrl?: string
  tokenCredential?: string
  modelVersion?: 'pipeline' | 'vlm'
  language?: string
  pollIntervalMs?: number
  pollJitterMs?: number
  timeoutMs?: number
}

interface MineruOutcome {
  api: 'precision'
  taskId: string
  state: string
  fullZipUrl?: string
}

interface CollectedPrecision {
  files: Array<{ name: string; path: string; bytes: number }>
  markdownText: string
  zipPath: string
}

interface MineruClientInstance {
  resolveApi(mode: 'precision', configured: 'precision'): { api: 'precision' }
  checkLocalFile(path: string, api: 'precision', maxBytes: number): Promise<{ size: number; ext: string }>
  submitAndWaitFile(input: {
    filePath: string
    fileName: string
    opts: Record<string, unknown>
    api: 'precision'
    signal: AbortSignal
  }): Promise<MineruOutcome>
  collectSingle(input: {
    outcome: MineruOutcome
    destDir: string
    opts: Record<string, unknown>
    signal: AbortSignal
  }): Promise<CollectedPrecision>
}

interface MineruRuntime {
  MineruClient: new (config: {
    baseUrl: string
    token: string
    userAgent: string
  }) => MineruClientInstance
}

const require = createRequire(import.meta.url)

async function loadMineruRuntime(): Promise<MineruRuntime> {
  const packageJson = require.resolve('dsh-mineru/package.json')
  const moduleUrl = pathToFileURL(join(dirname(packageJson), 'lib', 'mineru-client.js')).href
  return await import(moduleUrl) as MineruRuntime
}

export class MineruDocumentParser extends GerclawDocumentParser {
  static inject = ['credentials']
  static Config: z<Config> = z.object({
    apiBaseUrl: z.string().default('https://mineru.net'),
    tokenCredential: z.string().default('MINERU_API_KEY'),
    modelVersion: z.union([z.const('pipeline'), z.const('vlm')]).default('vlm'),
    language: z.string().default('ch'),
    pollIntervalMs: z.number().min(500).default(3000),
    pollJitterMs: z.number().min(0).default(500),
    timeoutMs: z.number().min(10_000).default(600_000),
  })

  private runtime: MineruRuntime | undefined

  constructor(ctx: Context, private readonly config: Config) {
    super(ctx)
  }

  protected async [Service.init](): Promise<void> {
    this.runtime = await loadMineruRuntime()
    this.ctx.effect(() => () => { this.runtime = undefined }, 'gerclaw.document-parser-mineru.runtime')
  }

  async parse(agent: Agent, sourcePath: string, name: string, signal: AbortSignal): Promise<ParsedDocument> {
    const runtime = this.runtime
    if (runtime === undefined) throw new Error('MinerU 文档解析服务尚未就绪')
    const cwd = agent.session.header.cwd
    if (cwd === undefined) throw new Error('当前对话尚未绑定工作区')
    const workspace = resolve(cwd)
    const source = resolve(sourcePath)
    if (source !== workspace && !source.startsWith(`${workspace}${sep}`))
      throw new Error('只能解析当前账号工作区中的文件')
    const hit = await this.ctx.credentials.resolve(credentialRef(this.config.tokenCredential ?? 'MINERU_API_KEY'))
    if (hit?.value === undefined || hit.value.length === 0)
      throw new Error('缺少必要变量 MINERU_API_KEY')
    const client = new runtime.MineruClient({
      baseUrl: this.config.apiBaseUrl ?? 'https://mineru.net',
      token: hit.value,
      userAgent: 'GerClaw document parser (dsh-mineru/0.1.9)',
    })
    const started = performance.now()
    const outputDir = join(workspace, '.dsh-mineru', 'artifacts', `gerclaw-${randomUUID()}`)
    const opts = {
      language: this.config.language ?? 'ch',
      enableTable: true,
      enableFormula: true,
      isOcr: false,
      modelVersion: this.config.modelVersion ?? 'vlm',
      extraFormats: [],
      timeoutMs: this.config.timeoutMs ?? 600_000,
      pollIntervalMs: this.config.pollIntervalMs ?? 3000,
      pollJitterMs: this.config.pollJitterMs ?? 500,
    }
    try {
      client.resolveApi('precision', 'precision')
      await client.checkLocalFile(source, 'precision', 10 * 1024 * 1024)
      const outcome = await client.submitAndWaitFile({
        filePath: source,
        fileName: name,
        opts,
        api: 'precision',
        signal,
      })
      await mkdir(outputDir, { recursive: true })
      const collected = await client.collectSingle({ outcome, destDir: outputDir, opts, signal })
      const markdown = collected.files.find(file => file.name === 'full.md' || file.name.endsWith('/full.md'))
      if (markdown === undefined || (await readFile(markdown.path, 'utf8')).trim().length === 0)
        throw new Error('MinerU 未返回可用的 Markdown 内容')
      await rm(collected.zipPath, { force: true })
      return {
        taskId: outcome.taskId,
        markdownPath: markdown.path,
        elapsedMs: Math.max(0, Math.round(performance.now() - started)),
        provider: 'MinerU',
      }
    } catch (error) {
      await rm(outputDir, { recursive: true, force: true })
      throw error
    }
  }
}

export default MineruDocumentParser
