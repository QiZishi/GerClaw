/** GerClaw user-facing HTTP application over native DSH services. */
import { randomUUID } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { basename, extname, join } from 'node:path'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { Context, Service } from '@deepseek-ai/cordis'
import type { AgentHandle } from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-plan-mode'
import type {} from '@deepseek-ai/dsh-goal'
import type {} from '@deepseek-ai/dsh-host-webserver'
import type {} from '@deepseek-ai/dsh-workspace'
import {
  defineDomain,
  domainTable,
  type Domain,
  type KvTable,
} from '@deepseek-ai/dsh-storage-domain'
import { SessionId } from '@deepseek-ai/dsh-session'
import { CallId, createUserMessage } from '@deepseek-ai/dsh-llm'
import type {} from '@deepseek-ai/dsh-tools'
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
const elapsed = (started: number) =>
  Math.max(0, Math.round(performance.now() - started))

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
    'agents',
    'planMode',
    'goals',
    'tools',
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
  private agentHandle!: AgentHandle
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
    const sessionId = SessionId('gerclaw-main')
    const primary = this.config.routes?.[0]
    const agentOptions = primary
      ? { provider: primary.provider, model: primary.model, maxTokens: 4096 }
      : { maxTokens: 4096 }
    try {
      this.agentHandle = await this.ctx.agents.resume({
        resumeSessionId: sessionId,
        agentOptions,
      })
    } catch {
      this.agentHandle = await this.ctx.agents.create({
        sessionId,
        meta: { cwd: this.config.dataDir },
        agentOptions,
      })
    }
    this.ctx.effect(
      () => () => this.agentHandle.dispose(),
      'gerclaw.app.agent',
    )
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
        const interaction = this.interactionSettings()
        const goal = this.ctx.goals.get(this.agentHandle.agent)
        json(res, 200, {
          audience: this.config.audience ?? 'patient',
          rag: this.ctx.gerclawRag.status(),
          profile: this.records.get('profile')?.value ?? null,
          tasks: (this.list('task') as TaskRun[]).slice(0, 30).map(task => ({
            ...task,
            artifacts: task.artifacts.map(({ artifactId, taskId, name, format, mediaType, size, createdAt }) => ({
              artifactId,
              taskId,
              name,
              format,
              mediaType,
              size,
              createdAt,
            })),
          })),
          artifacts: (this.list('artifact') as Array<ArtifactDescriptor & { path?: string }>)
            .slice(0, 100)
            .map(({ artifactId, taskId, name, format, mediaType, size, createdAt }) => ({
              artifactId,
              taskId,
              name,
              format,
              mediaType,
              size,
              createdAt,
            })),
          cga: this.list('cga').slice(0, 30),
          chronic: this.list('chronic').slice(0, 200),
          risks: this.list('risk').slice(0, 100),
          documents: this.list('document').slice(0, 100),
          interaction,
          modes: { plan: true, goal: true },
          goal,
        })
        return
      }
      if (method === 'PUT' && path === '/interaction') {
        const interaction = interactionSchema.parse(await readJson(req))
        if (interaction.mode === 'goal' && !interaction.goal) {
          throw new Error('目标模式需要先填写目标')
        }
        const agent = this.agentHandle.agent
        this.ctx.planMode.set(agent, interaction.mode === 'plan')
        let goal = this.ctx.goals.get(agent)
        if (interaction.mode === 'goal' && interaction.goal) {
          if (!goal || goal.phase === 'complete')
            goal = this.ctx.goals.create(agent, { objective: interaction.goal })
          else {
            if (goal.objective !== interaction.goal)
              goal = this.ctx.goals.edit(
                agent,
                { id: goal.id, revision: goal.revision },
                { objective: interaction.goal },
              )
            if (goal.phase === 'paused' || goal.phase === 'blocked')
              goal = this.ctx.goals.resume(agent, {
                id: goal.id,
                revision: goal.revision,
              })
          }
        } else if (goal?.phase === 'active') {
          goal = this.ctx.goals.pause(agent, {
            id: goal.id,
            revision: goal.revision,
          })
        }
        await this.put('interaction', 'interaction', interaction)
        json(res, 200, {
          ...interaction,
          plan: this.ctx.planMode.get(agent),
          goal,
        })
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
        let stepStarted = performance.now()
        const result = this.ctx.gerclawCga.score(input)
        const scoreMs = elapsed(stepStarted)
        stepStarted = performance.now()
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
        const persistMs = elapsed(stepStarted)
        const task = await this.completeTask('cga', '量表评分', input, result, [
          { name: '检查答案', summary: '答案完整且范围有效', elapsedMs: scoreMs },
          {
            name: '确定性计分',
            summary: `总分 ${result.score}，${result.severity}`,
            elapsedMs: scoreMs,
          },
          {
            name: '风险提示',
            summary: alerts.length
              ? `生成 ${alerts.length} 条提醒`
              : '未发现严重信号',
            elapsedMs: persistMs,
          },
        ])
        json(res, 200, { result, alerts, task })
        return
      }
      if (method === 'POST' && path === '/medication') {
        const input = (await readJson(
          req,
        )) as unknown as MedicationReviewRequest
        let stepStarted = performance.now()
        const result = this.ctx.gerclawMedicationReview.review(input)
        const reviewMs = elapsed(stepStarted)
        stepStarted = performance.now()
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
        const persistMs = elapsed(stepStarted)
        const task = await this.completeTask(
          'medication',
          '用药核对',
          input,
          result,
          [
            {
              name: '标准化药物清单',
              summary: `核对 ${result.reviewedMedications.length} 条记录`,
              elapsedMs: reviewMs,
            },
            {
              name: '执行规则 v4',
              summary: `命中 ${result.findings.length} 项`,
              elapsedMs: reviewMs,
            },
            {
              name: '附加来源与免责声明',
              summary: `引用 ${result.sources.length} 个规则来源`,
              elapsedMs: persistMs,
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
        let stepStarted = performance.now()
        const signal = this.ctx.gerclawCompanion.detect(text)
        const detectMs = elapsed(stepStarted)
        stepStarted = performance.now()
        const reply = signal.urgent
          ? (signal.message ?? '请立即联系家人、医生或当地紧急医疗服务。')
          : await this.directChat(text, COMPANION_SYSTEM_PROMPT, controller.signal)
        const replyMs = elapsed(stepStarted)
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
            { name: '理解当前感受', summary: '仅使用本次对话文字', elapsedMs: detectMs },
            {
              name: '检查紧急信号',
              summary: signal.urgent
                ? '发现需立即求助的信号'
                : '未发现紧急信号',
              elapsedMs: detectMs,
            },
            { name: '生成支持性回复', summary: '回复已完成', elapsedMs: replyMs },
          ],
        )
        json(res, 200, { reply, signal, alerts, task })
        return
      }
      if (method === 'POST' && path === '/chat') {
        const body = await readJson(req)
        const text = asText(body.text).trim()
        if (!text) throw new Error('请输入问题')
        const interaction = this.interactionSettings()
        const stepStarted = performance.now()
        const reply = await this.chat(text, controller.signal)
        const replyMs = elapsed(stepStarted)
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
              elapsedMs: Math.min(replyMs, 1),
            },
            { name: '调用健康助手', summary: '回复已生成', elapsedMs: replyMs },
            { name: '保存会话', summary: '会话已写入本账号日志', elapsedMs: 0 },
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
        const online = await this.ctx.gerclawMedicalEvidence.search(
          query,
          controller.signal,
        )
        json(res, 200, {
          results: [...local, ...online],
          rag: this.ctx.gerclawRag.status(),
        })
        return
      }
      if (method === 'POST' && path === '/prescription') {
        const body = (await readJson(req)) as unknown as PrescriptionRequest
        let stepStarted = performance.now()
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
        const evidenceMs = elapsed(stepStarted)
        stepStarted = performance.now()
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
        const generateMs = elapsed(stepStarted)
        const task = await this.completeTask(
          'prescription',
          '五大处方',
          body,
          result,
          [
            {
              name: '整理个人资料',
              summary: `健康目标 ${body.healthGoals.length} 项，当前问题 ${body.currentConcerns.length} 项`,
              elapsedMs: 0,
            },
            {
              name: '检索与排序证据',
              summary: `使用 ${evidence.length} 条可追溯证据`,
              elapsedMs: evidenceMs,
            },
            {
              name: '生成五大处方',
              summary: '药物、运动、营养、心理、康复五章已完成',
              elapsedMs: generateMs,
            },
            {
              name: '确定性用药附录',
              summary: result.medicationReview
                ? `命中 ${result.medicationReview.findings.length} 项`
                : '未提供用药清单',
              elapsedMs: 0,
            },
            { name: '保存结果', summary: '结果已保存，可导出下载', elapsedMs: 0 },
          ],
        )
        json(res, 200, { result, task })
        return
      }
      if (method === 'POST' && path === '/voice/tts') {
        const body = await readJson(req)
        const started = performance.now()
        res.writeHead(200, {
          'Content-Type': 'application/x-ndjson; charset=utf-8',
          'Cache-Control': 'no-store',
          'X-Content-Type-Options': 'nosniff',
        })
        res.write(JSON.stringify({
          type: 'meta',
          sampleRate: 24000,
          channels: 1,
          encoding: 'pcm16le',
        }) + '\n')
        for await (const chunk of this.ctx.gerclawVoice.synthesizeStream(
          asText(body.text),
          controller.signal,
        )) {
          res.write(JSON.stringify({
            type: 'audio',
            audio: Buffer.from(chunk.audio).toString('base64'),
          }) + '\n')
        }
        res.end(JSON.stringify({
          type: 'done',
          elapsedMs: Math.round(performance.now() - started),
        }) + '\n')
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
        let parseStatus = 'parsing'
        let parsedRef: string | undefined
        if (suffix === '.md' || suffix === '.txt') {
          await this.ctx.gerclawRag.addUserDocument(path, original)
          parseStatus = 'ready'
          parsedRef = path
        } else {
          const parsed = await this.ctx.tools.execute({
            callId: CallId(`gerclaw-mineru-${id}`),
            name: 'mineru_parse',
            arguments: {
              source: path,
              mode: 'precision',
              output: `gerclaw-${id}`,
            },
            signal: controller.signal,
            agent: this.agentHandle.agent,
          })
          if (parsed.isError)
            throw new Error(
              parsed.content
                .filter(block => block.type === 'text')
                .map(block => block.text)
                .join('\n') || 'MinerU 文档解析失败',
            )
          const meta = parsed.meta as { runDir?: string } | undefined
          if (!meta?.runDir) throw new Error('MinerU 未返回解析结果目录')
          const markdownPath = join(meta.runDir, 'full.md')
          await this.ctx.gerclawRag.addUserDocument(markdownPath, original)
          parseStatus = 'ready'
          parsedRef = markdownPath
        }
        const doc = {
          documentId: id,
          name: original,
          size: raw.length,
          createdAt: new Date().toISOString(),
          workspaceRef: `uploads/${id}${suffix}`,
          parseStatus,
          parsedRef,
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
  private async directChat(
    text: string,
    system: string | undefined,
    signal: AbortSignal,
  ): Promise<string> {
    const assembledSystem = system ?? GERCLAW_SYSTEM_PROMPT
    let last: unknown
    for (const route of (this.config.routes ?? []).slice(0, 1)) {
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
  private interactionSettings(): InteractionSettings {
    const plan = this.ctx.planMode.get(this.agentHandle.agent)
    const goal = this.ctx.goals.get(this.agentHandle.agent)
    if (plan.pending ?? plan.active) return { mode: 'plan' }
    if (goal?.phase === 'active')
      return { mode: 'goal', goal: goal.objective }
    return { mode: 'chat' }
  }

  private async chat(text: string, signal: AbortSignal): Promise<string> {
    const agent = this.agentHandle.agent
    const before = agent.session.deriveMessages().length
    const abort = () => {
      agent.cancel({ kind: 'user' })
    }
    signal.addEventListener('abort', abort, { once: true })
    try {
      agent.followup(createUserMessage({
        content: [{ type: 'text', text }],
        source: { kind: 'user' },
      }))
      await agent.whenIdle()
      signal.throwIfAborted()
      const messages = agent.session.deriveMessages().slice(before)
      const assistant = messages.toReversed().find(message => message.role === 'assistant')
      const reply = assistant?.content
        .filter(block => block.type === 'text')
        .map(block => block.text)
        .join('')
        .trim()
      if (!reply) throw new Error('模型没有返回可用内容')
      return reply
    } finally {
      signal.removeEventListener('abort', abort)
    }
  }
  private async completeTask(
    kind: string,
    _title: string,
    _input: unknown,
    result: unknown,
    steps: Array<{ name: string; summary: string; elapsedMs?: number }>,
  ): Promise<TaskRun> {
    const elapsedMs = steps.reduce(
      (total, step) => total + Math.max(0, step.elapsedMs ?? 0),
      0,
    )
    const ended = Date.now()
    const started = ended - elapsedMs
    let cursor = started
    const task: TaskRun = {
      taskId: randomUUID(),
      kind,
      status: 'completed',
      startedAt: new Date(started).toISOString(),
      endedAt: new Date(ended).toISOString(),
      elapsedMs,
      steps: steps.map((step) => {
        const stepStarted = cursor
        const stepElapsed = Math.max(0, step.elapsedMs ?? 0)
        cursor += stepElapsed
        return {
          name: step.name,
          status: 'completed' as const,
          startedAt: new Date(stepStarted).toISOString(),
          endedAt: new Date(cursor).toISOString(),
          elapsedMs: stepElapsed,
          summary: step.summary,
        }
      }),
      keyResults: steps.map(step => step.summary),
      result,
      artifacts: [],
    }
    await this.put(`task:${task.taskId}`, 'task', task)
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
      const descriptor: ArtifactDescriptor = {
        artifactId,
        taskId: task.taskId,
        name,
        format,
        mediaType: mediaTypes[format],
        size: content.length,
        createdAt: new Date().toISOString(),
      }
      await this.put(`artifact:${artifactId}`, 'artifact', {
        ...descriptor,
        path,
      })
      descriptors.push(descriptor)
    }
    task.artifacts.push(...descriptors)
    await this.put(`task:${task.taskId}`, 'task', task)
    return descriptors
  }
}
export default GerclawApp
