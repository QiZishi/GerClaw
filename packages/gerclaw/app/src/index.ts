/** GerClaw user-facing HTTP application over native DSH services. */
import { randomUUID } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { basename, extname, join } from 'node:path'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { Context, Service } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-host-webserver'
import type {} from '@deepseek-ai/dsh-workspace'
import {
  defineDomain,
  domainTable,
  type Domain,
  type KvTable,
} from '@deepseek-ai/dsh-storage-domain'
import { SessionId } from '@deepseek-ai/dsh-session'
import {
  createAssistantMessage,
  createUserMessage,
} from '@deepseek-ai/dsh-llm'
import { Document, Packer, Paragraph, HeadingLevel } from 'docx'
import { PDFDocument } from 'pdf-lib'
import sharp from 'sharp'
import { z } from 'zod'
import type { CgaAssessment } from '@gerclaw/cga'
import type { MedicationReviewRequest } from '@gerclaw/medication-review'
import type { HealthProfile } from '@gerclaw/health-profile'
import type { ChronicMeasurement } from '@gerclaw/chronic-care'
import { COMPANION_SYSTEM_PROMPT } from '@gerclaw/companion'
import type {} from '@gerclaw/medical-evidence'
import type {} from '@gerclaw/risk-alert'
import {
  evidenceFromLocalHits,
  type EvidenceSource,
  type PrescriptionRequest,
} from '@gerclaw/prescription'
import type {} from '@gerclaw/voice'
import type {} from '@gerclaw/local-rag'
import { GERCLAW_SYSTEM_PROMPT } from '@gerclaw/system-prompt'

export interface TaskStep {
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  startedAt?: string
  endedAt?: string
  elapsedMs?: number
  summary?: string
}
export interface ArtifactDescriptor {
  artifactId: string
  taskId: string
  name: string
  format: 'md' | 'html' | 'docx' | 'pdf' | 'png' | 'jpg' | 'json'
  mediaType: string
  size: number
  createdAt: string
}
export interface TaskRun {
  taskId: string
  kind: string
  status: 'running' | 'completed' | 'failed'
  startedAt: string
  endedAt?: string
  elapsedMs?: number
  steps: TaskStep[]
  keyResults: string[]
  result?: unknown
  artifacts: ArtifactDescriptor[]
  error?: string
}
type InteractionMode = 'chat' | 'plan' | 'goal'
interface InteractionSettings {
  mode: InteractionMode
  goal?: string
}
interface RecordValue {
  kind: string
  value: unknown
  updatedAt: string
}
const recordSchema = z.object({
  kind: z.string(),
  value: z.unknown(),
  updatedAt: z.string(),
})
const appDomainSpec = defineDomain({
  name: 'gerclaw_data',
  version: 1,
  tables: { records: domainTable<string, RecordValue>(recordSchema) },
})
export interface AppConfig {
  rootDir: string
  dataDir: string
  accountId: string
  audience?: 'doctor' | 'patient'
  routes?: Array<{ provider: string; model: string }>
}
const json = (res: ServerResponse, status: number, value: unknown) => {
  const body = JSON.stringify(value)
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    'Cache-Control': 'no-store',
  })
  res.end(body)
}
const safeError = (error: unknown) =>
  error instanceof Error
    ? error.message.replace(/(?:sk-|Bearer\s+)[A-Za-z0-9._-]+/g, '[已隐藏]')
    : '操作失败，请稍后重试'
const asText = (value: unknown): string =>
  typeof value === 'string' || typeof value === 'number'
    ? String(value)
    : ''
const interactionSchema = z.object({
  mode: z.enum(['chat', 'plan', 'goal']),
  goal: z.string().trim().max(500).optional(),
})
const readJson = async (
  req: IncomingMessage,
  max = 12 * 1024 * 1024,
): Promise<Record<string, unknown>> => {
  const chunks: Buffer[] = []
  let size = 0
  for await (const chunk of req as AsyncIterable<Uint8Array>) {
    const buffer = Buffer.from(chunk)
    size += buffer.length
    if (size > max) throw new Error('请求内容过大')
    chunks.push(buffer)
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8')) as Record<
      string,
      unknown
    >
  } catch {
    throw new Error('请求格式无效')
  }
}
const escapeXml = (value: string) =>
  value.replace(
    /[&<>"']/g,
    char =>
      ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&apos;',
      })[char] ?? char,
  )
const renderText = (title: string, value: unknown): string =>
  `# ${title}\n\n${JSON.stringify(value, null, 2)}\n`
const renderHtml = (title: string, text: string) =>
  `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>${escapeXml(title)}</title><style>body{font:16px/1.75 system-ui;max-width:900px;margin:40px auto;padding:0 24px;color:#21352d}pre{white-space:pre-wrap;background:#f4f8f5;padding:24px;border-radius:16px}</style><h1>${escapeXml(title)}</h1><pre>${escapeXml(text)}</pre></html>`
const renderSvg = (title: string, text: string) => {
  const lines = [title, ...text.split('\n')].slice(0, 90)
  const height = Math.max(800, 100 + lines.length * 30)
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="${height}"><rect width="100%" height="100%" fill="#f7fbf8"/><text x="70" y="75" font-family="PingFang SC,Noto Sans CJK SC,sans-serif" font-size="38" font-weight="700" fill="#173d30">${escapeXml(lines[0] ?? title)}</text>${lines
    .slice(1)
    .map(
      (line, index) =>
        `<text x="70" y="${130 + index * 30}" font-family="PingFang SC,Noto Sans CJK SC,sans-serif" font-size="19" fill="#304a40">${escapeXml(line.slice(0, 100))}</text>`,
    )
    .join('')}</svg>`
}
const mediaTypes = {
  md: 'text/markdown; charset=utf-8',
  html: 'text/html; charset=utf-8',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pdf: 'application/pdf',
  png: 'image/png',
  jpg: 'image/jpeg',
  json: 'application/json; charset=utf-8',
} as const

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawApp: GerclawApp
  }
}
export class GerclawApp extends Service {
  static inject = [
    'webServer',
    'storageDomain',
    'sessions',
    'sessionPersistence',
    'llm',
    'workspaceRegistry',
    'gerclawCga',
    'gerclawMedicationReview',
    'gerclawMedicalEvidence',
    'gerclawHealthProfile',
    'gerclawChronicCare',
    'gerclawRiskAlert',
    'gerclawCompanion',
    'gerclawPrescription',
    'gerclawVoice',
    'gerclawRag',
  ]
  private domain!: Domain<typeof appDomainSpec>
  private records!: KvTable<string, RecordValue>
  private readonly controllers = new Set<AbortController>()
  constructor(
    ctx: Context,
    private readonly config: AppConfig,
  ) {
    super(ctx, 'gerclawApp')
  }
  protected async [Service.init](): Promise<void> {
    await mkdir(this.config.dataDir, { recursive: true })
    await mkdir(join(this.config.dataDir, 'uploads'), { recursive: true })
    await mkdir(join(this.config.dataDir, 'artifacts'), { recursive: true })
    this.domain = await this.ctx.storageDomain.open(appDomainSpec)
    this.records = this.domain.table('records')
    await this.ctx.workspaceRegistry.create(this.config.dataDir, 'GerClaw')
    this.ctx.effect(() => () => this.domain.close(), 'gerclaw.app.domain')
    this.ctx.effect(
      () => () => {
        for (const controller of this.controllers) controller.abort()
        this.controllers.clear()
      },
      'gerclaw.app.requests',
    )
    const dispose = this.ctx.webServer.register({
      kind: 'prefix',
      path: '/gerclaw/api',
      handler: (req, res) => this.handle(req, res),
    })
    const fallback = this.ctx.webServer.registerFallback((req, res) =>
      this.serve(req, res),
    )
    this.ctx.effect(
      () => () => {
        dispose()
        fallback()
      },
      'gerclaw.app.http',
    )
  }
  private put(key: string, kind: string, value: unknown) {
    return this.records.put(key, {
      kind,
      value,
      updatedAt: new Date().toISOString(),
    })
  }
  private list(kind: string): unknown[] {
    return [...this.records.entries()]
      .filter(([, entry]) => entry.kind === kind)
      .sort((a, b) => b[1].updatedAt.localeCompare(a[1].updatedAt))
      .map(([, entry]) => entry.value)
  }
  private async serve(req: IncomingMessage, res: ServerResponse) {
    const path = new URL(
      req.url ?? '/',
      `http://${req.headers.host ?? 'localhost'}`,
    ).pathname
    if (path === '/icon.png') {
      const content = await readFile(join(this.config.rootDir, 'icon.png'))
      res.writeHead(200, {
        'Content-Type': 'image/png',
        'Cache-Control': 'public, max-age=3600',
      })
      res.end(content)
      return
    }
    if (path !== '/' && !path.startsWith('/index')) {
      json(res, 404, { error: '页面不存在' })
      return
    }
    const content = await readFile(
      new URL('../public/index.html', import.meta.url),
    )
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    })
    res.end(content)
  }
  private async handle(req: IncomingMessage, res: ServerResponse) {
    const controller = new AbortController()
    this.controllers.add(controller)
    req.once('aborted', () => {
      controller.abort()
    })
    res.once('close', () => {
      if (!res.writableEnded) controller.abort()
    })
    try {
      const url = new URL(
        req.url ?? '/',
        `http://${req.headers.host ?? 'localhost'}`,
      )
      const path = url.pathname.replace('/gerclaw/api', '') || '/'
      const method = req.method ?? 'GET'
      if (method === 'GET' && path === '/bootstrap') {
        const interaction = (this.records.get('interaction')?.value ?? {
          mode: 'chat',
        }) as InteractionSettings
        json(res, 200, {
          accountId: this.config.accountId,
          audience: this.config.audience ?? 'patient',
          rag: this.ctx.gerclawRag.status(),
          profile: this.records.get('profile')?.value ?? null,
          tasks: this.list('task').slice(0, 30),
          artifacts: this.list('artifact').slice(0, 100),
          cga: this.list('cga').slice(0, 30),
          chronic: this.list('chronic').slice(0, 200),
          risks: this.list('risk').slice(0, 100),
          documents: this.list('document').slice(0, 100),
          interaction,
          modes: { plan: true, goal: true },
        })
        return
      }
      if (method === 'PUT' && path === '/interaction') {
        const interaction = interactionSchema.parse(await readJson(req))
        if (interaction.mode === 'goal' && !interaction.goal) {
          throw new Error('目标模式需要先填写目标')
        }
        await this.put('interaction', 'interaction', interaction)
        json(res, 200, interaction)
        return
      }
      if (method === 'PUT' && path === '/profile') {
        const body = await readJson(req)
        const prior = this.records.get('profile')?.value as
          | HealthProfile
          | undefined
        const profile = this.ctx.gerclawHealthProfile.normalize(
          body,
          prior,
        )
        await this.put('profile', 'profile', profile)
        json(res, 200, profile)
        return
      }
      if (method === 'POST' && path === '/cga') {
        const input = (await readJson(req)) as unknown as CgaAssessment
        const result = this.ctx.gerclawCga.score(input)
        const id = randomUUID()
        await this.put(`cga:${id}`, 'cga', {
          id,
          input,
          result,
          createdAt: new Date().toISOString(),
        })
        const alerts = this.ctx.gerclawRiskAlert.derive({ cga: result })
        await Promise.all(
          alerts.map(alert =>
            this.put(`risk:${alert.alertId}`, 'risk', alert),
          ),
        )
        const task = await this.completeTask('cga', '量表评分', input, result, [
          { name: '检查答案', summary: '答案完整且范围有效' },
          {
            name: '确定性计分',
            summary: `总分 ${result.score}，${result.severity}`,
          },
          {
            name: '风险提示',
            summary: alerts.length
              ? `生成 ${alerts.length} 条提醒`
              : '未发现严重信号',
          },
        ])
        json(res, 200, { result, alerts, task })
        return
      }
      if (method === 'POST' && path === '/medication') {
        const input = (await readJson(
          req,
        )) as unknown as MedicationReviewRequest
        const result = this.ctx.gerclawMedicationReview.review(input)
        const id = randomUUID()
        await this.put(`medication:${id}`, 'medication', {
          id,
          input,
          result,
          createdAt: new Date().toISOString(),
        })
        const alerts = this.ctx.gerclawRiskAlert.derive({ medication: result })
        await Promise.all(
          alerts.map(alert =>
            this.put(`risk:${alert.alertId}`, 'risk', alert),
          ),
        )
        const task = await this.completeTask(
          'medication',
          '用药核对',
          input,
          result,
          [
            {
              name: '标准化药物清单',
              summary: `核对 ${result.reviewedMedications.length} 条记录`,
            },
            {
              name: '执行规则 v4',
              summary: `命中 ${result.findings.length} 项`,
            },
            {
              name: '附加来源与免责声明',
              summary: `引用 ${result.sources.length} 个规则来源`,
            },
          ],
        )
        json(res, 200, { result, alerts, task })
        return
      }
      if (method === 'POST' && path === '/chronic') {
        const body = await readJson(req)
        const value = Number(body.value)
        if (!Number.isFinite(value) || value < 0 || value > 10_000_000)
          throw new Error('请输入有效的非负测量值')
        const item: ChronicMeasurement = {
          measurementId: randomUUID(),
          conditionId: asText(body.conditionId) || 'default',
          metricLabel: asText(body.metricLabel).trim(),
          value,
          unit: asText(body.unit).trim(),
          measuredAt: asText(body.measuredAt) || new Date().toISOString(),
          createdAt: new Date().toISOString(),
        }
        if (!item.metricLabel || !item.unit)
          throw new Error('请填写指标和单位')
        await this.put(`chronic:${item.measurementId}`, 'chronic', item)
        const trends = this.ctx.gerclawChronicCare.trends(
          this.list('chronic') as ChronicMeasurement[],
        )
        json(res, 200, { item, trends })
        return
      }
      if (method === 'POST' && path === '/companion') {
        const body = await readJson(req)
        const text = asText(body.text).trim()
        if (!text) throw new Error('请输入想说的话')
        const signal = this.ctx.gerclawCompanion.detect(text)
        const reply = signal.urgent
          ? (signal.message ?? '请立即联系家人、医生或当地紧急医疗服务。')
          : await this.chat(text, COMPANION_SYSTEM_PROMPT, controller.signal)
        const alerts = this.ctx.gerclawRiskAlert.derive({ companion: signal })
        await Promise.all(
          alerts.map(alert =>
            this.put(`risk:${alert.alertId}`, 'risk', alert),
          ),
        )
        const task = await this.completeTask(
          'companion',
          '陪伴对话',
          { text },
          reply,
          [
            { name: '理解当前感受', summary: '仅使用本次对话文字' },
            {
              name: '检查紧急信号',
              summary: signal.urgent
                ? '发现需立即求助的信号'
                : '未发现紧急信号',
            },
            { name: '生成支持性回复', summary: '回复已完成' },
          ],
        )
        json(res, 200, { reply, signal, alerts, task })
        return
      }
      if (method === 'POST' && path === '/chat') {
        const body = await readJson(req)
        const text = asText(body.text).trim()
        if (!text) throw new Error('请输入问题')
        const interaction = (this.records.get('interaction')?.value ?? {
          mode: 'chat',
        }) as InteractionSettings
        const basePrompt = GERCLAW_SYSTEM_PROMPT
        const modePrompt =
          interaction.mode === 'plan'
            ? '\n\n当前为计划模式：先澄清健康任务的目标和约束，再给出可执行、可调整的分步计划；除非用户明确要求，不直接宣称已执行计划中的操作。'
            : interaction.mode === 'goal'
              ? `\n\n当前为目标模式。持续目标：${interaction.goal}。围绕目标推进本轮工作，说明当前进展、下一步和仍需用户决定的事项。`
              : ''
        const reply = await this.chat(
          text,
          `${basePrompt}${modePrompt}`,
          controller.signal,
        )
        const task = await this.completeTask(
          'chat',
          '智能对话',
          { text },
          reply,
          [
            {
              name: '理解问题',
              summary:
                interaction.mode === 'plan'
                  ? '已按计划模式整理任务'
                  : interaction.mode === 'goal'
                    ? '已按持续目标整理任务'
                    : '已整理本次问题',
            },
            { name: '调用健康助手', summary: '回复已生成' },
            { name: '保存会话', summary: '会话已写入本账号日志' },
          ],
        )
        json(res, 200, { reply, task })
        return
      }
      if (method === 'POST' && path === '/evidence') {
        const body = await readJson(req)
        const query = asText(body.query).trim()
        if (!query) throw new Error('请输入检索词')
        const local = evidenceFromLocalHits(
          await this.ctx.gerclawRag.search(query, 8),
        )
        const evidenceAbort = new AbortController()
        let timeout: ReturnType<typeof setTimeout> | undefined
        const online = await Promise.race([
          this.ctx.gerclawMedicalEvidence
            .search(query, evidenceAbort.signal)
            .catch(() => []),
          new Promise<EvidenceSource[]>((resolve) => {
            timeout = setTimeout(() => {
              resolve([])
            }, 5_000)
          }),
        ])
        if (timeout) clearTimeout(timeout)
        evidenceAbort.abort()
        json(res, 200, {
          results: [...local, ...online],
          rag: this.ctx.gerclawRag.status(),
        })
        return
      }
      if (method === 'POST' && path === '/prescription') {
        const body = (await readJson(req)) as unknown as PrescriptionRequest
        let evidence = Array.isArray(body.evidence) ? body.evidence : []
        if (evidence.length === 0) {
          const query = [...body.healthGoals, ...body.currentConcerns].join(' ')
          evidence = evidenceFromLocalHits(
            await this.ctx.gerclawRag.search(query, 8),
          )
          if (evidence.length === 0)
            evidence = await this.ctx.gerclawMedicalEvidence.search(
              query,
              controller.signal,
            )
        }
        const profile = this.records.get('profile')?.value
        const result = await this.ctx.gerclawPrescription.generate(
          {
            ...body,
            evidence,
            profileSummary:
              profile === undefined ? '' : JSON.stringify(profile),
          },
          controller.signal,
        )
        const task = await this.completeTask(
          'prescription',
          '五大处方',
          body,
          result,
          [
            {
              name: '整理个人资料',
              summary: `健康目标 ${body.healthGoals.length} 项，当前问题 ${body.currentConcerns.length} 项`,
            },
            {
              name: '检索与排序证据',
              summary: `使用 ${evidence.length} 条可追溯证据`,
            },
            {
              name: '生成五大处方',
              summary: '药物、运动、营养、心理、康复五章已完成',
            },
            {
              name: '确定性用药附录',
              summary: result.medicationReview
                ? `命中 ${result.medicationReview.findings.length} 项`
                : '未提供用药清单',
            },
            { name: '保存结果', summary: '结果已保存，可导出下载' },
          ],
        )
        json(res, 200, { result, task })
        return
      }
      if (method === 'POST' && path === '/voice/asr') {
        const body = await readJson(req)
        const audio = Buffer.from(asText(body.audio), 'base64')
        const format = asText(body.format)
        if (format !== 'wav' && format !== 'mp3' && format !== 'webm')
          throw new Error('录音格式无效')
        const result = await this.ctx.gerclawVoice.transcribe(
          audio,
          format,
          controller.signal,
        )
        json(res, 200, result)
        return
      }
      if (method === 'POST' && path === '/voice/tts') {
        const body = await readJson(req)
        const result = await this.ctx.gerclawVoice.synthesize(
          asText(body.text),
          undefined,
          controller.signal,
        )
        res.writeHead(200, {
          'Content-Type': 'audio/L16; rate=24000; channels=1',
          'X-GerClaw-Elapsed-Ms': String(result.elapsedMs),
          'Cache-Control': 'no-store',
        })
        res.end(result.audio)
        return
      }
      if (method === 'POST' && path === '/documents') {
        const body = await readJson(req)
        const raw = Buffer.from(asText(body.data), 'base64')
        if (raw.length === 0 || raw.length > 10 * 1024 * 1024)
          throw new Error('文件大小必须在 1 字节到 10 MB 之间')
        const original = basename(asText(body.name) || 'document').slice(
          0,
          160,
        )
        const suffix = extname(original).toLowerCase()
        if (!['.pdf', '.md', '.txt', '.docx'].includes(suffix))
          throw new Error('支持 PDF、Markdown、TXT 和 DOCX 文件')
        const id = randomUUID()
        const path = join(this.config.dataDir, 'uploads', `${id}${suffix}`)
        await writeFile(path, raw, { flag: 'wx' })
        const doc = {
          documentId: id,
          name: original,
          size: raw.length,
          createdAt: new Date().toISOString(),
          workspaceRef: `uploads/${id}${suffix}`,
          parseStatus:
            suffix === '.md' || suffix === '.txt'
              ? 'ready'
              : 'queued-for-mineru',
        }
        if (suffix === '.md' || suffix === '.txt') {
          await this.ctx.gerclawRag.addUserDocument(path, original)
        }
        await this.put(`document:${id}`, 'document', doc)
        json(res, 201, doc)
        return
      }
      if (method === 'POST' && path === '/artifacts/export') {
        const body = await readJson(req)
        const taskId = asText(body.taskId)
        const task = this.records.get(`task:${taskId}`)?.value as
          | TaskRun
          | undefined
        if (!task) throw new Error('未找到该结果')
        const formats = (
          Array.isArray(body.formats)
            ? body.formats
            : ['md', 'html', 'docx', 'pdf', 'png', 'jpg', 'json']
        )
          .map(String)
          .filter(
            format => format in mediaTypes,
          ) as ArtifactDescriptor['format'][]
        const artifacts = await this.exportTask(task, formats)
        json(res, 200, { artifacts })
        return
      }
      if (method === 'GET' && path.startsWith('/artifacts/')) {
        const id = path.slice('/artifacts/'.length)
        const descriptor = this.records.get(`artifact:${id}`)?.value as
          | (ArtifactDescriptor & { path?: string })
          | undefined
        if (!descriptor?.path) throw new Error('产物不存在')
        const content = await readFile(descriptor.path)
        res.writeHead(200, {
          'Content-Type': descriptor.mediaType,
          'Content-Disposition': `attachment; filename*=UTF-8''${encodeURIComponent(descriptor.name)}`,
          'Content-Length': content.length,
          'Cache-Control': 'private, no-store',
        })
        res.end(content)
        return
      }
      json(res, 404, { error: '接口不存在' })
    } catch (error) {
      if (!controller.signal.aborted) {
        json(res, 400, { error: safeError(error) })
      }
    } finally {
      this.controllers.delete(controller)
    }
  }
  private async chat(
    text: string,
    system: string | undefined,
    signal: AbortSignal,
  ): Promise<string> {
    const assembledSystem = system ?? GERCLAW_SYSTEM_PROMPT
    let last: unknown
    for (const route of this.config.routes ?? []) {
      try {
        if (process.env.GERCLAW_DIAGNOSTICS === '1') {
          console.error(`[GerClaw model route start] ${route.provider}`)
        }
        let chunks = 0
        const chunkTypes: string[] = []
        let reply = ''
        let completedText = ''
        let streamFailure: string | undefined
        for await (const chunk of this.ctx.llm.stream({
          provider: route.provider,
          model: route.model,
          messages: [
            createUserMessage({
              content: [{ type: 'text', text }],
              source: { kind: 'user' },
            }),
          ],
          system: assembledSystem,
          maxTokens: 1600,
          temperature: 0.4,
          signal,
        })) {
          chunks += 1
          chunkTypes.push(chunk.type)
          if (chunk.type === 'text-delta') reply += chunk.text
          else if (chunk.type === 'block-end' && chunk.block.type === 'text') {
            completedText += chunk.block.text
            const completedReply = (reply || completedText).trim()
            if (completedReply) {
              setTimeout(() => {
                this.logSession(
                  text,
                  completedReply,
                  route.provider,
                  route.model,
                )
              }, 0)
              return completedReply
            }
          }
          else if (
            chunk.type === 'finish' &&
            (chunk.reason.kind === 'error' || chunk.reason.kind === 'aborted')
          ) {
            streamFailure = chunk.reason.failure.message
            if (process.env.GERCLAW_DIAGNOSTICS === '1') {
              console.error(
                `[GerClaw model finish failure] ${route.provider}: ${chunk.reason.failure.code}`,
              )
            }
          }
        }
        if (process.env.GERCLAW_DIAGNOSTICS === '1') {
          console.error(
            `[GerClaw model route complete] ${route.provider}: ${chunks} chunks`,
            chunkTypes.join(','),
          )
        }
        if (streamFailure) throw new Error(streamFailure)
        reply = (reply || completedText).trim()
        if (process.env.GERCLAW_DIAGNOSTICS === '1') {
          console.error(
            `[GerClaw model text] ${route.provider}: ${reply.length} chars`,
          )
        }
        if (!reply) throw new Error('模型没有返回可用内容')
        this.logSession(text, reply, route.provider, route.model)
        return reply
      } catch (error) {
        if (signal.aborted) throw error
        if (process.env.GERCLAW_DIAGNOSTICS === '1') {
          console.error(
            `[GerClaw model route failed] ${route.provider}: ${safeError(error)}`,
          )
        }
        last = error
      }
    }
    throw new Error(`模型服务不可用：${safeError(last)}`)
  }
  private logSession(
    input: string,
    output: string,
    provider: string,
    model: string,
  ) {
    const trace = (stage: string) => {
      if (process.env.GERCLAW_DIAGNOSTICS === '1')
        console.error(`[GerClaw session] ${stage}`)
    }
    trace('create')
    const id = SessionId(`gerclaw-${randomUUID()}`)
    const session = this.ctx.sessions.create(id, {
      meta: { cwd: this.config.dataDir },
    })
    trace('append')
    session.append('turn/start', { turn: 1 })
    session.append('step/start', { turn: 1, step: 1 })
    session.append(
      'user/message',
      createUserMessage({
        content: [{ type: 'text', text: input }],
        source: { kind: 'user' },
      }),
      { surfaceOp: 'append' },
    )
    session.append(
      'assistant/message',
      {
        turn: 1,
        step: 1,
        message: createAssistantMessage({
          content: [{ type: 'text', text: output }],
          source: { provider, model },
        }),
      },
      { surfaceOp: 'append', sourceEventSeqs: [] },
    )
    session.append('step/end', { turn: 1, step: 1 })
    session.append('turn/end', { turn: 1, reason: { kind: 'completed' } })
    trace('flush-scheduled')
    void this.ctx.sessions.flush(session).catch((error: unknown) => {
      if (process.env.GERCLAW_DIAGNOSTICS === '1') {
        console.error(`[GerClaw session flush failed] ${safeError(error)}`)
      }
    })
    trace('return')
  }
  private async completeTask(
    kind: string,
    title: string,
    input: unknown,
    result: unknown,
    steps: Array<{ name: string; summary: string }>,
  ): Promise<TaskRun> {
    const started = Date.now()
    const now = new Date().toISOString()
    const task: TaskRun = {
      taskId: randomUUID(),
      kind,
      status: 'completed',
      startedAt: now,
      endedAt: new Date().toISOString(),
      elapsedMs: Date.now() - started,
      steps: steps.map((step, index) => ({
        name: step.name,
        status: 'completed',
        startedAt: now,
        endedAt: new Date().toISOString(),
        elapsedMs: index === 0 ? 1 : 0,
        summary: step.summary,
      })),
      keyResults: steps.map(step => step.summary),
      result,
      artifacts: [],
    }
    await this.put(`task:${task.taskId}`, 'task', task)
    this.logSession(
      `${title}\n${JSON.stringify(input)}`,
      `${title}已完成\n${JSON.stringify(result)}`,
      'gerclaw',
      kind,
    )
    return task
  }
  private async exportTask(
    task: TaskRun,
    formats: ArtifactDescriptor['format'][],
  ): Promise<ArtifactDescriptor[]> {
    const title = `GerClaw ${task.kind} 结果`
    const markdown = renderText(title, task.result)
    const svg = renderSvg(title, markdown)
    const png = await sharp(Buffer.from(svg)).png().toBuffer()
    const files = new Map<ArtifactDescriptor['format'], Buffer>()
    files.set('md', Buffer.from(markdown))
    files.set('html', Buffer.from(renderHtml(title, markdown)))
    files.set('json', Buffer.from(JSON.stringify(task.result, null, 2)))
    files.set('png', png)
    files.set('jpg', await sharp(png).jpeg({ quality: 92 }).toBuffer())
    const doc = new Document({
      sections: [
        {
          children: [
            new Paragraph({ text: title, heading: HeadingLevel.TITLE }),
            ...markdown.split('\n').map(line => new Paragraph(line)),
          ],
        },
      ],
    })
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
      if (!content) throw new Error('导出格式不可用')
      const artifactId = randomUUID()
      const name = `gerclaw-${task.kind}-${task.taskId.slice(0, 8)}.${format}`
      const path = join(
        this.config.dataDir,
        'artifacts',
        `${artifactId}.${format}`,
      )
      await writeFile(path, content, { flag: 'wx' })
      const descriptor: ArtifactDescriptor & { path: string } = {
        artifactId,
        taskId: task.taskId,
        name,
        format,
        mediaType: mediaTypes[format],
        size: content.length,
        createdAt: new Date().toISOString(),
        path,
      }
      await this.put(`artifact:${artifactId}`, 'artifact', descriptor)
      descriptors.push(descriptor)
    }
    task.artifacts.push(...descriptors)
    await this.put(`task:${task.taskId}`, 'task', task)
    return descriptors
  }
}
export default GerclawApp
