/** Local Workspace artifact provider for GerClaw normalized medical results. */
import { createHash, randomUUID } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { basename, extname, join, relative, resolve, sep } from 'node:path'
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
  type DocumentDescriptor,
  type DocumentFile,
  type StoredDocument,
} from '@gerclaw/artifact'
import type {} from '@gerclaw/health-repository'
import type {} from '@deepseek-ai/dsh-fs'

export interface Config { dataDir: string; accountId: string }

interface StoredArtifact extends ArtifactDescriptor {
  accountId?: string
  sessionId: string
  absolutePath?: string
}
interface StoredDocumentRecord extends DocumentDescriptor {
  accountId?: string
  sessionId?: string
  sourcePath?: string
}

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
  static inject = ['healthRepository', 'workspaceRegistry', 'fs']
  static Config: z<Config> = z.object({
    dataDir: z.string(),
    accountId: z.string().default('local'),
  })
  private readonly accountId: string
  private readonly root: string

  constructor(ctx: Context, config: Config) {
    super(ctx)
    this.accountId = config.accountId
    this.root = resolve(config.dataDir)
  }

  protected async [Service.init](): Promise<void> {
    // Files are created lazily beneath the exact Agent session cwd. The
    // provider must not use one process-global artifact root.
  }

  async export(agent: Agent, source: ArtifactSource, formats: ArtifactFormat[]): Promise<ArtifactDescriptor[]> {
    if (source.sessionId === undefined || source.sessionId !== String(agent.id))
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
      const absolutePath = await this.writeWorkspaceFile(agent, workspaceRef, format, content)
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
        accountId: this.accountId,
        absolutePath,
      }
      await this.ctx.healthRepository.put(`artifact:${artifactId}`, 'artifact', descriptor)
      descriptors.push(this.publicDescriptor(descriptor))
    }
    return descriptors
  }

  list(agent?: Agent): ArtifactDescriptor[] {
    return this.ctx.healthRepository.list<StoredArtifact>('artifact')
      .filter(item => this.belongsToCurrentAccount(item.accountId)
        && (agent === undefined || item.sessionId === String(agent.id)))
      .map(item => this.publicDescriptor(item))
  }

  async read(artifactId: string): Promise<ArtifactFile | undefined> {
    const stored = this.ctx.healthRepository.get(`artifact:${artifactId}`) as StoredArtifact | undefined
    if (stored === undefined) return undefined
    if (!this.belongsToCurrentAccount(stored.accountId)) throw new Error('该结果不属于当前账号')
    const expectedPath = stored.absolutePath === undefined
      ? this.resolveLegacyPath(join('conversations', stored.workspaceRef))
      : this.resolveLegacyPath(stored.absolutePath)
    return { descriptor: this.publicDescriptor(stored), content: await readFile(expectedPath) }
  }

  async storeDocument(agent: Agent, name: string, content: Uint8Array): Promise<StoredDocument> {
    const original = basename(name || 'document').slice(0, 160)
    const suffix = extname(original).toLowerCase()
    const documentId = randomUUID()
    const workspaceRef = `uploads/${documentId}${suffix}`
    const sourcePath = await this.writeBinaryWorkspaceFile(agent, workspaceRef, content)
    const descriptor: DocumentDescriptor = {
      documentId,
      name: original,
      size: content.byteLength,
      createdAt: new Date().toISOString(),
      workspaceRef,
      parseStatus: 'pending',
    }
    const record: StoredDocumentRecord = {
      ...descriptor,
      accountId: this.accountId,
      sessionId: String(agent.id),
      sourcePath,
    }
    await this.ctx.healthRepository.put(`document:${documentId}`, 'document', record)
    return { descriptor, sourcePath }
  }

  async updateDocument(
    agent: Agent,
    documentId: string,
    patch: Pick<DocumentDescriptor, 'parseStatus' | 'parsedRef'>,
  ): Promise<DocumentDescriptor> {
    const record = this.getDocument(agent, documentId)
    const parsedRef = patch.parsedRef === undefined
      ? undefined
      : await this.normalizeWorkspaceRef(agent, patch.parsedRef)
    const updated: StoredDocumentRecord = {
      ...record,
      ...patch,
      ...(parsedRef === undefined ? {} : { parsedRef }),
    }
    await this.ctx.healthRepository.put(`document:${documentId}`, 'document', updated)
    return this.publicDocument(updated)
  }

  listDocuments(agent?: Agent): DocumentDescriptor[] {
    void agent
    return this.ctx.healthRepository.list<StoredDocumentRecord>('document')
      .filter(item => this.belongsToCurrentAccount(item.accountId))
      .map(item => this.publicDocument(item))
  }

  async readDocument(documentId: string): Promise<DocumentFile | undefined> {
    const record = this.ctx.healthRepository.get(`document:${documentId}`) as StoredDocumentRecord | undefined
    if (record === undefined) return undefined
    if (!this.belongsToCurrentAccount(record.accountId)) throw new Error('该资料不属于当前账号')
    const content = record.sourcePath === undefined
      ? await readFile(this.resolveLegacyPath(record.workspaceRef))
      : await readFile(this.resolveLegacyPath(record.sourcePath))
    return { descriptor: this.publicDocument(record), content }
  }

  async readDocumentText(agent: Agent, documentId: string): Promise<string> {
    const record = this.getDocument(agent, documentId)
    if (record.parsedRef === undefined) throw new Error('上传资料尚未解析完成')
    if (resolve(record.parsedRef) === record.parsedRef)
      return readFile(this.resolveLegacyPath(record.parsedRef), 'utf8')
    const target = await this.resolveWorkspaceTarget(agent, record.parsedRef)
    return this.ctx.fs.readText(target)
  }

  private assertOwned(agent: Agent, stored: StoredArtifact): void {
    void agent
    if (!this.belongsToCurrentAccount(stored.accountId)) throw new Error('该结果不属于当前账号')
  }

  private assertDocumentOwned(agent: Agent, stored: StoredDocumentRecord): void {
    void agent
    if (!this.belongsToCurrentAccount(stored.accountId)) throw new Error('该资料不属于当前账号')
  }

  private belongsToCurrentAccount(accountId: string | undefined): boolean {
    // Legacy records predate explicit owner metadata but already live inside
    // one account-isolated Host/storage domain, so they belong to this Host.
    return accountId === undefined || accountId === this.accountId
  }

  private getDocument(agent: Agent, documentId: string): StoredDocumentRecord {
    const record = this.ctx.healthRepository.get(`document:${documentId}`) as StoredDocumentRecord | undefined
    if (record === undefined) throw new Error('文档不存在')
    this.assertDocumentOwned(agent, record)
    return record
  }

  private workspaceCwd(agent: Agent): string {
    const cwd = agent.session.header.cwd
    if (cwd === undefined || cwd.trim().length === 0) throw new Error('当前对话尚未绑定工作区')
    return resolve(cwd)
  }

  private async resolveWorkspaceTarget(agent: Agent, workspaceRef: string) {
    const cwd = this.workspaceCwd(agent)
    const workspace = await this.ctx.fs.resolve('.', { cwd })
    const target = await this.ctx.fs.resolve(workspaceRef, { cwd })
    if (!this.ctx.fs.contains(workspace, target)) throw new Error('工作区路径无效')
    return target
  }

  private async resolveWorkspacePath(agent: Agent, workspaceRef: string): Promise<string> {
    const target = await this.resolveWorkspaceTarget(agent, workspaceRef)
    return this.ctx.fs.processPath(target)
  }

  private resolveLegacyPath(path: string): string {
    const absolute = resolve(this.root, path)
    if (absolute !== this.root && !absolute.startsWith(`${this.root}${sep}`))
      throw new Error('工作区路径无效')
    return absolute
  }

  private async normalizeWorkspaceRef(agent: Agent, path: string): Promise<string> {
    const absolutePath = await this.resolveWorkspacePath(agent, path)
    const workspaceRef = relative(this.workspaceCwd(agent), absolutePath)
    if (workspaceRef === '' || workspaceRef.startsWith('..')) throw new Error('工作区路径无效')
    return workspaceRef
  }

  private async writeWorkspaceFile(
    agent: Agent,
    workspaceRef: string,
    format: ArtifactFormat,
    content: Buffer,
  ): Promise<string> {
    const target = await this.resolveWorkspaceTarget(agent, workspaceRef)
    const absolutePath = this.ctx.fs.processPath(target)
    await mkdir(join(this.workspaceCwd(agent), 'artifacts'), { recursive: true })
    if (format === 'md' || format === 'html' || format === 'json') {
      await this.ctx.fs.writeText(target, content.toString('utf8'))
    } else {
      await writeFile(absolutePath, content, { flag: 'wx' })
    }
    return absolutePath
  }

  private async writeBinaryWorkspaceFile(agent: Agent, workspaceRef: string, content: Uint8Array): Promise<string> {
    const target = await this.resolveWorkspaceTarget(agent, workspaceRef)
    const absolutePath = this.ctx.fs.processPath(target)
    await mkdir(join(this.workspaceCwd(agent), 'uploads'), { recursive: true })
    await writeFile(absolutePath, content, { flag: 'wx' })
    return absolutePath
  }

  private publicDescriptor(stored: StoredArtifact): ArtifactDescriptor {
    const { accountId: _account, absolutePath: _legacyPath, sessionId: _session, ...descriptor } = stored
    return descriptor
  }

  private publicDocument(stored: StoredDocumentRecord): DocumentDescriptor {
    const { accountId: _account, sessionId: _session, sourcePath: _path, ...descriptor } = stored
    return descriptor
  }
}

export default LocalGerclawArtifactService
