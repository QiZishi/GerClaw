/** Local Workspace artifact provider for GerClaw normalized medical results. */
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { join, resolve, sep } from 'node:path'
import { Context, Service } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-workspace'
import z from '@deepseek-ai/schemastery'
import { Document, HeadingLevel, Packer, Paragraph } from 'docx'
import { PDFDocument } from 'pdf-lib'
import sharp from 'sharp'
import {
  GerclawArtifactService,
  type ArtifactDescriptor,
  type ArtifactFile,
  type ArtifactFormat,
  type ArtifactSource,
} from '@gerclaw/artifact'
import type {} from '@gerclaw/health-repository'

export interface Config { dataDir: string }

interface StoredArtifact extends ArtifactDescriptor { absolutePath: string }

const mediaTypes: Record<ArtifactFormat, string> = {
  md: 'text/markdown; charset=utf-8',
  html: 'text/html; charset=utf-8',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pdf: 'application/pdf',
  png: 'image/png',
  jpg: 'image/jpeg',
  json: 'application/json; charset=utf-8',
}

const escapeXml = (value: string): string => value.replace(/[&<>"']/gu, character => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;',
})[character] ?? character)

const markdownOf = (title: string, result: unknown): string =>
  `# ${title}\n\n${JSON.stringify(result, null, 2)}\n`

const htmlOf = (title: string, markdown: string): string =>
  `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>${escapeXml(title)}</title><style>body{font:16px/1.75 system-ui;max-width:900px;margin:40px auto;padding:0 24px;color:#173a55}pre{white-space:pre-wrap;background:#f0f7fc;padding:24px;border-radius:16px}</style><h1>${escapeXml(title)}</h1><pre>${escapeXml(markdown)}</pre></html>`

const svgOf = (title: string, markdown: string): string => {
  const lines = [title, ...markdown.split('\n')].slice(0, 90)
  const height = Math.max(800, 100 + lines.length * 30)
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="${height}"><rect width="100%" height="100%" fill="#f4f9fd"/><text x="70" y="75" font-family="PingFang SC,Noto Sans CJK SC,sans-serif" font-size="38" font-weight="700" fill="#173a55">${escapeXml(lines[0] ?? title)}</text>${lines.slice(1).map((line, index) => `<text x="70" y="${130 + index * 30}" font-family="PingFang SC,Noto Sans CJK SC,sans-serif" font-size="19" fill="#35566d">${escapeXml(line.slice(0, 100))}</text>`).join('')}</svg>`
}

export class LocalGerclawArtifactService extends GerclawArtifactService {
  static inject = ['healthRepository', 'workspaceRegistry']
  static Config: z<Config> = z.object({ dataDir: z.string() })
  private readonly root: string

  constructor(ctx: Context, config: Config) {
    super(ctx)
    this.root = resolve(config.dataDir)
  }

  protected async [Service.init](): Promise<void> {
    await mkdir(join(this.root, 'artifacts'), { recursive: true })
    await this.ctx.workspaceRegistry.create(this.root, 'GerClaw')
  }

  async export(agent: Agent, source: ArtifactSource, formats: ArtifactFormat[]): Promise<ArtifactDescriptor[]> {
    if (source.sessionId !== undefined && source.sessionId !== agent.id)
      throw new Error('该结果不属于当前对话')
    const title = `GerClaw ${source.kind} 结果`
    const markdown = markdownOf(title, source.result)
    const svg = svgOf(title, markdown)
    const png = await sharp(Buffer.from(svg)).png().toBuffer()
    const files = new Map<ArtifactFormat, Buffer>([
      ['md', Buffer.from(markdown)],
      ['html', Buffer.from(htmlOf(title, markdown))],
      ['json', Buffer.from(JSON.stringify(source.result, null, 2))],
      ['png', png],
      ['jpg', await sharp(png).jpeg({ quality: 92 }).toBuffer()],
    ])
    const doc = new Document({ sections: [{ children: [
      new Paragraph({ text: title, heading: HeadingLevel.TITLE }),
      ...markdown.split('\n').map(line => new Paragraph(line)),
    ] }] })
    files.set('docx', Buffer.from(await Packer.toBuffer(doc)))
    const pdf = await PDFDocument.create()
    const embedded = await pdf.embedPng(png)
    const width = 595
    const height = Math.min(5000, (embedded.height * width) / embedded.width)
    const page = pdf.addPage([width, height])
    page.drawImage(embedded, { x: 0, y: 0, width, height })
    files.set('pdf', Buffer.from(await pdf.save()))

    const descriptors: ArtifactDescriptor[] = []
    for (const format of [...new Set(formats)]) {
      const content = files.get(format)
      if (content === undefined) throw new Error('导出格式不可用')
      const artifactId = createHash('sha256')
        .update(`${source.taskId}\0${format}\0`).update(content).digest('hex')
      const stored = this.ctx.healthRepository.get(`artifact:${artifactId}`) as StoredArtifact | undefined
      if (stored !== undefined) {
        this.assertOwned(agent, stored)
        descriptors.push(this.publicDescriptor(stored))
        continue
      }
      const name = `gerclaw-${source.kind}-${source.taskId.slice(0, 8)}.${format}`
      const workspaceRef = `artifacts/${artifactId}.${format}`
      const absolutePath = this.resolveWorkspaceRef(workspaceRef)
      await writeFile(absolutePath, content, { flag: 'wx' })
      const descriptor: StoredArtifact = {
        artifactId,
        taskId: source.taskId,
        sessionId: String(agent.id),
        name,
        workspaceRef,
        format,
        mediaType: mediaTypes[format],
        size: content.length,
        createdAt: new Date().toISOString(),
        absolutePath,
      }
      await this.ctx.healthRepository.put(`artifact:${artifactId}`, 'artifact', descriptor)
      descriptors.push(this.publicDescriptor(descriptor))
    }
    return descriptors
  }

  list(agent?: Agent): ArtifactDescriptor[] {
    return this.ctx.healthRepository.list<StoredArtifact>('artifact')
      .filter(item => agent === undefined || item.sessionId === agent.id)
      .map(item => this.publicDescriptor(item))
  }

  async read(artifactId: string): Promise<ArtifactFile | undefined> {
    const stored = this.ctx.healthRepository.get(`artifact:${artifactId}`) as StoredArtifact | undefined
    if (stored === undefined) return undefined
    const expectedPath = this.resolveWorkspaceRef(stored.workspaceRef)
    if (stored.absolutePath !== expectedPath) throw new Error('产物路径无效')
    return { descriptor: this.publicDescriptor(stored), content: await readFile(expectedPath) }
  }

  private assertOwned(agent: Agent, stored: StoredArtifact): void {
    if (stored.sessionId !== agent.id) throw new Error('该产物不属于当前对话')
  }

  private resolveWorkspaceRef(workspaceRef: string): string {
    const absolute = resolve(this.root, workspaceRef)
    if (absolute !== this.root && !absolute.startsWith(`${this.root}${sep}`))
      throw new Error('产物路径无效')
    return absolute
  }

  private publicDescriptor(stored: StoredArtifact): ArtifactDescriptor {
    const { absolutePath: _hidden, ...descriptor } = stored
    return descriptor
  }
}

export default LocalGerclawArtifactService
