/** DSH Jobs-backed GerClaw medical task provider. */
import { randomUUID } from 'node:crypto'
import { Service } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import type { JobId as JobIdType, JobOutcome } from '@deepseek-ai/dsh-jobs'
import type {} from '@deepseek-ai/dsh-subagent'
import type { CgaAssessment, CgaResult } from '@gerclaw/cga'
import type { ChronicMeasurement } from '@gerclaw/chronic-care'
import { COMPANION_SYSTEM_PROMPT } from '@gerclaw/companion'
import type { HealthProfile } from '@gerclaw/health-profile'
import { evidenceFromLocalHits } from '@gerclaw/prescription'
import type { MedicationReviewRequest } from '@gerclaw/medication-review'
import {
  GerclawTaskRuntime,
  type CompletedTaskInput,
  type GerclawJsonValue,
  type MedicalTaskCancelRequest,
  type MedicalTaskCancelResult,
  type MedicalTaskExportRequest,
  type MedicalTaskExportResult,
  type MedicalTaskKind,
  type MedicalTaskStatusRequest,
  type MedicalTaskStatusResult,
  type MedicalTaskSubmitRequest,
  type MedicalTaskSubmitResult,
  type TaskRun,
} from '@gerclaw/task-runtime'
import type {} from '@gerclaw/artifact'
import type {} from '@gerclaw/health-repository'
import type {} from '@gerclaw/library'
import type {} from '@gerclaw/medical-evidence'
import type {} from '@gerclaw/risk-alert'

declare module '@deepseek-ai/dsh-jobs' {
  interface JobKindMap { gerclaw: 'gerclaw' }
}

const elapsed = (started: number): number => Math.max(0, Math.round(performance.now() - started))
const asText = (value: unknown): string => typeof value === 'string' || typeof value === 'number' ? String(value) : ''
const asObject = (value: GerclawJsonValue): Record<string, GerclawJsonValue> => {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    throw new Error('任务输入格式无效')
  return value
}
const toJsonValue = (value: unknown): GerclawJsonValue => JSON.parse(JSON.stringify(value)) as GerclawJsonValue
const safeError = (error: unknown): string => error instanceof Error
  ? error.message.replace(/(?:sk-|Bearer\s+)[A-Za-z0-9._-]+/gu, '[已隐藏]')
  : '操作失败，请稍后重试'

export class LocalGerclawTaskRuntime extends GerclawTaskRuntime {
  static inject = [
    'jobs', 'sessions', 'subagents', 'healthRepository', 'gerclawArtifacts',
    'gerclawCga', 'gerclawMedicationReview', 'gerclawMedicalEvidence',
    'gerclawHealthProfile', 'gerclawChronicCare', 'gerclawRiskAlert',
    'gerclawCompanion', 'gerclawRag',
  ]

  protected [Service.init](): void {
    this.ctx.effect(
      () => this.ctx.jobs.attachController('gerclaw-task-runtime'),
      'gerclaw.task-runtime.jobs-controller',
    )
  }

  async submit(
    agent: Agent,
    request: MedicalTaskSubmitRequest,
    signal: AbortSignal,
  ): Promise<MedicalTaskSubmitResult> {
    const requestId = request.requestId.trim()
    if (!/^[A-Za-z0-9_-]{8,128}$/u.test(requestId)) throw new Error('任务请求编号无效')
    const label = `GerClaw:${requestId}`
    if (this.ctx.jobs.list(agent).some(job => job.label === label
      && (job.status === 'running' || job.status === 'stopping'))) {
      throw new Error('该任务正在处理中')
    }

    const controller = new AbortController()
    let resolveDone!: (outcome: JobOutcome) => void
    const done = new Promise<JobOutcome>((resolve) => { resolveDone = resolve })
    let resolveResult!: (result: MedicalTaskSubmitResult) => void
    let rejectResult!: (error: unknown) => void
    const result = new Promise<MedicalTaskSubmitResult>((resolve, reject) => {
      resolveResult = resolve
      rejectResult = reject
    })

    const jobId: JobIdType = this.ctx.jobs.start({
      kind: 'gerclaw',
      label,
      owner: agent,
      run: () => {
        queueMicrotask(() => {
          void this.runOwnedTask(agent, String(jobId), request.kind, request.input, controller.signal)
            .then((completed) => {
              resolveResult(completed)
              resolveDone({ status: 'completed', detail: request.kind })
            }, async (error: unknown) => {
              const cancelled = controller.signal.aborted
              await this.failTask(agent, String(jobId), request.kind, error, cancelled)
              rejectResult(error)
              resolveDone({
                status: cancelled ? 'killed' : 'failed',
                detail: cancelled ? '用户停止任务' : safeError(error),
              })
            })
        })
        return {
          cancel: (reason) => { controller.abort(new Error(reason ?? '用户停止任务')) },
          done,
        }
      },
    })

    const abort = (): void => {
      try { this.ctx.jobs.kill(jobId, agent, '请求已取消') } catch { controller.abort(signal.reason) }
    }
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) abort()
    try {
      return await result
    } finally {
      signal.removeEventListener('abort', abort)
    }
  }

  cancel(agent: Agent, request: MedicalTaskCancelRequest): MedicalTaskCancelResult {
    const label = `GerClaw:${request.requestId.trim()}`
    const job = this.ctx.jobs.list(agent).find(candidate => candidate.label === label
      && (candidate.status === 'running' || candidate.status === 'stopping'))
    if (job === undefined) return { cancelled: false }
    const result = this.ctx.jobs.kill(job.id, agent, '用户停止任务')
    return result === 'requested'
      ? { cancelled: true, taskId: String(job.id) }
      : { cancelled: false, taskId: String(job.id) }
  }

  status(agent: Agent, request: MedicalTaskStatusRequest): MedicalTaskStatusResult {
    const task = this.ctx.healthRepository.get(`task:${request.taskId}`) as TaskRun | undefined
    return { task: task?.sessionId === agent.id ? task : null }
  }

  async export(agent: Agent, request: MedicalTaskExportRequest): Promise<MedicalTaskExportResult> {
    const task = this.ctx.healthRepository.get(`task:${request.taskId}`) as TaskRun | undefined
    if (task === undefined) throw new Error('未找到该结果')
    if (task.sessionId !== agent.id) throw new Error('该结果不属于当前对话')
    if (task.status !== 'completed' || task.result === undefined) throw new Error('任务尚未完成，不能导出')
    const formats = [...new Set(request.formats)]
    if (formats.length === 0) throw new Error('请选择至少一种导出格式')
    const artifacts = await this.ctx.gerclawArtifacts.export(agent, {
      taskId: task.taskId,
      sessionId: task.sessionId,
      kind: task.kind,
      result: task.result,
    }, formats)
    const known = new Set(task.artifacts.map(item => item.artifactId))
    const updated = { ...task, artifacts: [...task.artifacts, ...artifacts.filter(item => !known.has(item.artifactId))] }
    await this.recordTask(agent, updated)
    return { artifacts }
  }

  async complete(agent: Agent, input: CompletedTaskInput): Promise<TaskRun> {
    const elapsedMs = input.steps.reduce((total, step) => total + Math.max(0, step.elapsedMs ?? 0), 0)
    const ended = Date.now()
    let cursor = ended - elapsedMs
    const taskId = input.taskId ?? `gerclaw-${randomUUID()}`
    if (this.ctx.healthRepository.get(`task:${taskId}`) === undefined) {
      await this.recordTask(agent, {
        taskId,
        sessionId: String(agent.id),
        kind: input.kind,
        status: 'running',
        startedAt: new Date(cursor).toISOString(),
        steps: [{ name: '准备任务', status: 'running', startedAt: new Date(cursor).toISOString() }],
        keyResults: [],
        artifacts: [],
      })
    }
    const task: TaskRun = {
      taskId,
      sessionId: String(agent.id),
      kind: input.kind,
      status: 'completed',
      startedAt: new Date(cursor).toISOString(),
      endedAt: new Date(ended).toISOString(),
      elapsedMs,
      steps: input.steps.map((step) => {
        const startedAt = cursor
        const duration = Math.max(0, step.elapsedMs ?? 0)
        cursor += duration
        return {
          name: step.name,
          status: 'completed' as const,
          startedAt: new Date(startedAt).toISOString(),
          endedAt: new Date(cursor).toISOString(),
          elapsedMs: duration,
          summary: step.summary,
        }
      }),
      keyResults: input.steps.map(step => step.summary),
      result: toJsonValue(input.result),
      artifacts: [],
    }
    await this.recordTask(agent, task)
    return task
  }

  private async runOwnedTask(
    agent: Agent,
    taskId: string,
    kind: MedicalTaskKind,
    input: GerclawJsonValue,
    signal: AbortSignal,
  ): Promise<MedicalTaskSubmitResult> {
    const startedAt = new Date().toISOString()
    await this.recordTask(agent, {
      taskId,
      sessionId: String(agent.id),
      kind,
      status: 'running',
      startedAt,
      steps: [{ name: '准备任务', status: 'running', startedAt }],
      keyResults: [],
      artifacts: [],
    })
    const completed = await this.executeMedicalTask(agent, kind, input, signal, taskId)
    return { task: completed.task, response: toJsonValue(completed.response) }
  }

  private async failTask(
    agent: Agent,
    taskId: string,
    kind: MedicalTaskKind,
    error: unknown,
    cancelled: boolean,
  ): Promise<void> {
    const prior = this.ctx.healthRepository.get(`task:${taskId}`) as TaskRun | undefined
    const startedAt = prior?.startedAt ?? new Date().toISOString()
    const endedAt = new Date().toISOString()
    await this.recordTask(agent, {
      taskId,
      sessionId: String(agent.id),
      kind,
      status: cancelled ? 'cancelled' : 'failed',
      startedAt,
      endedAt,
      elapsedMs: Math.max(0, Date.parse(endedAt) - Date.parse(startedAt)),
      steps: [{
        name: cancelled ? '任务已停止' : '任务未完成',
        status: 'failed',
        startedAt,
        endedAt,
        summary: cancelled ? '已按用户要求停止' : safeError(error),
      }],
      keyResults: [],
      artifacts: prior?.artifacts ?? [],
      error: cancelled ? '任务已停止' : safeError(error),
    })
  }

  private async recordTask(agent: Agent, task: TaskRun): Promise<void> {
    await this.ctx.healthRepository.put(`task:${task.taskId}`, 'task', task)
    agent.session.append('gerclaw/task', { version: 1, turn: null, task })
    await this.ctx.sessions.flush(agent.session)
  }

  private async executeMedicalTask(
    agent: Agent,
    kind: MedicalTaskKind,
    input: GerclawJsonValue,
    signal: AbortSignal,
    taskId: string,
  ): Promise<{ task: TaskRun; response: unknown }> {
    const body = asObject(input)
    signal.throwIfAborted()
    if (kind === 'profile') {
      let stepStarted = performance.now()
      const prior = this.ctx.healthRepository.get('profile') as HealthProfile | undefined
      const profile = this.ctx.gerclawHealthProfile.normalize(body, prior)
      const normalizeMs = elapsed(stepStarted)
      stepStarted = performance.now()
      await this.ctx.healthRepository.put('profile', 'profile', profile)
      const persistMs = elapsed(stepStarted)
      const task = await this.complete(agent, { taskId, kind, result: profile, steps: [
        { name: '检查档案字段', summary: '年龄与结构化资料格式有效', elapsedMs: normalizeMs },
        { name: '保存账号档案', summary: '已保存为本账号权威健康资料', elapsedMs: persistMs },
      ] })
      return { task, response: { result: profile, task } }
    }
    if (kind === 'cga') {
      let stepStarted = performance.now()
      const assessment = body as unknown as CgaAssessment
      const result = this.scoreCgaWithHistory(assessment)
      const scoreMs = elapsed(stepStarted)
      stepStarted = performance.now()
      const id = randomUUID()
      await this.ctx.healthRepository.put(`cga:${id}`, 'cga', { id, input: assessment, result, createdAt: new Date().toISOString() })
      const alerts = this.ctx.gerclawRiskAlert.derive({ cga: result })
      await Promise.all(alerts.map(alert => this.ctx.healthRepository.put(`risk:${alert.alertId}`, 'risk', alert)))
      const persistMs = elapsed(stepStarted)
      const task = await this.complete(agent, { taskId, kind, result, steps: [
        { name: '检查答案', summary: '答案完整且范围有效', elapsedMs: scoreMs },
        { name: '确定性计分', summary: `总分 ${result.score}，${result.severity}`, elapsedMs: scoreMs },
        { name: '风险提示', summary: alerts.length ? `生成 ${alerts.length} 条提醒` : '未发现严重信号', elapsedMs: persistMs },
      ] })
      return { task, response: { result, alerts, task } }
    }
    if (kind === 'medication') {
      let stepStarted = performance.now()
      const request = body as unknown as MedicationReviewRequest
      const result = this.ctx.gerclawMedicationReview.review(request)
      const reviewMs = elapsed(stepStarted)
      stepStarted = performance.now()
      const id = randomUUID()
      await this.ctx.healthRepository.put(`medication:${id}`, 'medication', { id, input: request, result, createdAt: new Date().toISOString() })
      const alerts = this.ctx.gerclawRiskAlert.derive({ medication: result })
      await Promise.all(alerts.map(alert => this.ctx.healthRepository.put(`risk:${alert.alertId}`, 'risk', alert)))
      const persistMs = elapsed(stepStarted)
      const task = await this.complete(agent, { taskId, kind, result, steps: [
        { name: '标准化药物清单', summary: `核对 ${result.reviewedMedications.length} 条记录`, elapsedMs: reviewMs },
        { name: '执行规则 v4', summary: `命中 ${result.findings.length} 项`, elapsedMs: reviewMs },
        { name: '附加来源与免责声明', summary: `引用 ${result.sources.length} 个规则来源`, elapsedMs: persistMs },
      ] })
      return { task, response: { result, alerts, task } }
    }
    if (kind === 'chronic') {
      let stepStarted = performance.now()
      const item = await this.recordChronic({
        conditionId: asText(body.conditionId) || 'default',
        metricLabel: asText(body.metricLabel),
        value: Number(body.value),
        unit: asText(body.unit),
        ...(asText(body.measuredAt) ? { measuredAt: asText(body.measuredAt) } : {}),
      })
      const persistMs = elapsed(stepStarted)
      stepStarted = performance.now()
      const trends = this.ctx.gerclawChronicCare.trends(this.ctx.healthRepository.list<ChronicMeasurement>('chronic'))
      const trendMs = elapsed(stepStarted)
      const result = { item, trends }
      const task = await this.complete(agent, { taskId, kind, result, steps: [
        { name: '保存本次测量', summary: `${item.metricLabel} ${item.value} ${item.unit}`, elapsedMs: persistMs },
        { name: '计算变化趋势', summary: `当前趋势：${item.direction}`, elapsedMs: trendMs },
      ] })
      return { task, response: { result, item, trends, task } }
    }
    if (kind === 'companion') {
      const text = asText(body.text).trim()
      if (!text) throw new Error('请输入想说的话')
      let stepStarted = performance.now()
      const companionSignal = this.ctx.gerclawCompanion.detect(text)
      const detectMs = elapsed(stepStarted)
      stepStarted = performance.now()
      const reply = companionSignal.urgent
        ? (companionSignal.message ?? '请立即联系家人、医生或当地紧急医疗服务。')
        : await this.runSubagentText(agent, text, signal)
      const replyMs = elapsed(stepStarted)
      const alerts = this.ctx.gerclawRiskAlert.derive({ companion: companionSignal })
      await Promise.all(alerts.map(alert => this.ctx.healthRepository.put(`risk:${alert.alertId}`, 'risk', alert)))
      const task = await this.complete(agent, { taskId, kind, result: reply, steps: [
        { name: '理解当前感受', summary: '仅使用本次对话文字', elapsedMs: detectMs },
        { name: '检查紧急信号', summary: companionSignal.urgent ? '发现需立即求助的信号' : '未发现紧急信号', elapsedMs: detectMs },
        { name: '生成支持性回复', summary: '回复已完成', elapsedMs: replyMs },
      ] })
      return { task, response: { reply, signal: companionSignal, alerts, task } }
    }
    const query = asText(body.query).trim()
    if (!query) throw new Error('请输入检索词')
    let stepStarted = performance.now()
    const local = evidenceFromLocalHits(await this.ctx.gerclawRag.search(query, 8, signal))
    const localMs = elapsed(stepStarted)
    stepStarted = performance.now()
    const onlineSearch = await this.ctx.gerclawMedicalEvidence.searchDetailed(query, signal)
    const failedSources = onlineSearch.sources.filter(source => source.status === 'failed')
    if (failedSources.length > 0) {
      throw new Error(failedSources
        .map(source => `${source.source}：${source.error ?? '服务暂时不可用'}`)
        .join('；'))
    }
    const online = onlineSearch.results
    const onlineMs = elapsed(stepStarted)
    const result = {
      results: [...local, ...online],
      sources: onlineSearch.sources,
      rag: this.ctx.gerclawRag.status(),
    }
    const task = await this.complete(agent, { taskId, kind, result, steps: [
      { name: '检索本地知识库', summary: `找到 ${local.length} 条可回溯资料`, elapsedMs: localMs },
      { name: '检索权威医学来源', summary: `找到 ${online.length} 条在线资料`, elapsedMs: onlineMs },
      { name: '整理引用结果', summary: `共 ${result.results.length} 条结果`, elapsedMs: 0 },
    ] })
    return { task, response: { ...result, result, task } }
  }

  private scoreCgaWithHistory(input: CgaAssessment): CgaResult {
    const current = this.ctx.gerclawCga.score(input)
    const previous = this.ctx.healthRepository.list<{ result?: CgaResult; createdAt?: string }>('cga')
      .find(record => record.result?.kind === input.kind)
    return this.ctx.gerclawCga.compare(current, previous?.result === undefined ? undefined : {
      result: previous.result,
      ...(previous.createdAt === undefined ? {} : { completedAt: previous.createdAt }),
    })
  }

  private async recordChronic(input: {
    conditionId: string
    metricLabel: string
    value: number
    unit: string
    measuredAt?: string
  }) {
    if (!Number.isFinite(input.value) || input.value < 0 || input.value > 10_000_000)
      throw new Error('请输入有效的非负测量值')
    const metricLabel = input.metricLabel.trim()
    const unit = input.unit.trim()
    if (!metricLabel || !unit) throw new Error('请填写指标和单位')
    const item: ChronicMeasurement = {
      measurementId: randomUUID(),
      conditionId: input.conditionId.trim() || 'default',
      metricLabel,
      value: input.value,
      unit,
      measuredAt: input.measuredAt?.trim() || new Date().toISOString(),
      createdAt: new Date().toISOString(),
    }
    await this.ctx.healthRepository.put(`chronic:${item.measurementId}`, 'chronic', item)
    const direction = this.ctx.gerclawChronicCare
      .trends(this.ctx.healthRepository.list<ChronicMeasurement>('chronic'))
      .find(trend =>
        trend.conditionId === item.conditionId
        && trend.metricLabel === item.metricLabel
        && trend.unit === item.unit,
      )?.direction ?? 'first'
    return { ...item, direction }
  }

  private async runSubagentText(agent: Agent, text: string, signal: AbortSignal): Promise<string> {
    const run = await agent.ctx.subagents.start('spawn', {
      label: '生成支持性回复', parent: agent, signal,
      prompt: [{ type: 'text', text }], persona: COMPANION_SYSTEM_PROMPT,
      maxDepth: 1, toolFilter: { allow: [] }, agentOptions: { maxTokens: 1600 },
    })
    try {
      const outcome = await run.result
      if (outcome.stopReason !== 'completed') throw new Error(outcome.diagnostic ?? '支持性回复生成未完成')
      const reply = outcome.output.filter(block => block.type === 'text').map(block => block.text).join('').trim()
      if (!reply) throw new Error('模型没有返回可用内容')
      return reply
    } finally {
      await run.dispose()
    }
  }
}

export default LocalGerclawTaskRuntime
