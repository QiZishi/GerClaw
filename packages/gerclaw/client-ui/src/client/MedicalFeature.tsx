import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import type {
  ArtifactDescriptor,
  GerclawJsonValue,
  MedicalTaskKind,
  MedicalTaskSubmitResult,
} from '@gerclaw/app/types'
import type { FeatureId } from './MedicalNavigation.tsx'
import {
  mmseGroups,
  mmseOptions,
  phq9Options,
  phq9Questions,
  psqiComponentLabels,
  psqiDaytimeOptions,
  psqiDisturbanceQuestions,
  psqiFrequencyOptions,
  psqiPartnerOptions,
  psqiQualityOptions,
  sasOptions,
  sasQuestions,
  type CgaOption,
} from './cga-definitions.ts'

type JsonObject = Record<string, unknown>
export type TaskStep = { name?: string; summary?: string; elapsedMs?: number; status?: string }
export type Task = {
  taskId?: string
  kind?: string
  status?: 'running' | 'completed' | 'failed' | 'cancelled'
  elapsedMs?: number
  steps?: TaskStep[]
  result?: unknown
  artifacts?: unknown[]
}
export type Response = { result?: unknown; task?: Task; alerts?: unknown[]; [key: string]: unknown }

export interface MedicalRemoteActions {
  submit: (
    kind: MedicalTaskKind,
    sessionId: string,
    input: GerclawJsonValue,
    requestId: string,
    signal: AbortSignal,
  ) => Promise<MedicalTaskSubmitResult>
  cancel: (sessionId: string, requestId: string) => Promise<boolean>
  export: (sessionId: string, taskId: string, formats: ArtifactDescriptor['format'][]) => Promise<ArtifactDescriptor[]>
}

const labels: Record<string, string> = {
  medication: '药物处方', exercise: '运动处方', nutrition: '营养处方',
  psychological: '心理处方', rehabilitation: '康复处方', goal: '目标',
  recommendations: '建议', precautions: '注意事项', conclusion: '结论',
  disclaimer: '重要说明', severity: '结果分级', score: '总分', followUp: '后续建议',
  findings: '核对发现', clinicianAction: '建议行动', title: '项目', summary: '摘要',
  healthAssessment: '健康评估', sections: '五大处方', evidenceSources: '参考证据',
  patientSummary: '个人情况摘要', keyIssues: '需要关注', riskFactors: '风险因素',
  status: '复核状态', age: '年龄', sex: '性别', healthGoals: '健康目标',
  currentConcerns: '当前问题', clinicianReviewRequired: '需要专业复核',
  medicationReview: '用药核对附录', patientAge: '年龄',
  reviewedMedications: '已核对药物', position: '序号', text: '录入内容',
  recognizedGenericNames: '识别到的药物', unrecognizedEntryCount: '未识别记录数',
  involvedGenericNames: '涉及药物', elderlyNote: '老年用药提示',
  ageEscalated: '因年龄提高风险等级', source: '资料来源',
  locator: '原文位置', snippet: '原文摘录', url: '原文链接', components: '分项得分',
  safetyAlert: '紧急提示', displayName: '称呼', allergies: '过敏史',
  conditions: '已有疾病', medications: '当前用药', goals: '健康目标',
  preferences: '个人偏好', metricLabel: '指标', value: '数值', unit: '单位',
  measuredAt: '测量时间', direction: '趋势', reply: '回复', urgent: '紧急信号',
  content: '建议内容',
  item: '本次测量', trends: '趋势分析', conditionId: '管理项目',
  latestValue: '本次测量值', previousValue: '上次测量值',
  latestMeasuredAt: '本次测量时间', previousMeasuredAt: '上次测量时间',
  message: '提醒内容', action: '建议行动',
  results: '检索结果',
  comparison: '与上次同量表比较', previousScore: '上次得分', delta: '分数变化',
  previousCompletedAt: '上次完成时间',
  ...psqiComponentLabels,
}

const hiddenResultKeys = new Set([
  'templateVersion', 'modelOutputSchemaVersion', 'profileId', 'revision',
  'rulesetVersion', 'findingId', 'sourceIds', 'evidenceId', 'evidenceIds',
  'source_id', 'content_sha256', 'review_status', 'coverage', 'sources',
  'details', 'kind', 'uploadedDocumentRefs', 'evidenceSources',
  'version', 'measurementId', 'createdAt', 'alertId', 'sourceRecordId', 'rag',
])

const valueLabels: Record<string, string> = {
  needs_clinician_review: '需要专业人员复核',
  unknown: '未填写', female: '女', male: '男', other: '其他',
  routine: '常规随访', priority: '优先随访', immediate: '立即处理',
  contraindicated: '禁忌', major: '高风险', moderate: '中等风险', minor: '低风险',
  up: '上升', down: '下降', stable: '平稳', insufficient: '数据不足',
  unchanged: '平稳', first: '首次记录，暂无趋势',
  high: '高风险', critical: '紧急风险', active: '待处理', resolved: '已处理',
  improved: '改善', worsened: '需关注',
  medication_review: '用药核对', cga: '综合量表', companion: '暖心陪伴',
}

const friendlyText = (value: string): string =>
  (valueLabels[value] ?? value)
    .replace(/\[local_[A-Za-z0-9_-]+\]/gu, '〔本地证据〕')

const api = async (sessionId: string, path: string, init: RequestInit = {}): Promise<Response> => {
  const headers = new Headers(init.headers)
  headers.set('content-type', 'application/json')
  headers.set('x-gerclaw-session-id', sessionId)
  const response = await fetch(`/gerclaw/api${path}`, {
    ...init,
    headers,
  })
  const rawPayload: unknown = await response.json().catch((): unknown => ({}))
  const payload = (typeof rawPayload === 'object' && rawPayload !== null ? rawPayload : {}) as Response & { error?: string }
  if (!response.ok) throw new Error(payload.error ?? '操作没有完成，请稍后重试')
  return payload
}

const lineList = (value: string): string[] => value.split(/[\n；;]/u).map(row => row.trim()).filter(Boolean)
const seconds = (value = 0): string => value < 10 ? '< 0.01 秒' : `${(value / 1000).toFixed(2)} 秒`

function StructuredValue({ value, depth = 0 }: { value: unknown; depth?: number }): ReactNode {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'boolean') return <span>{value ? '是' : '否'}</span>
  if (typeof value === 'string') return <span>{friendlyText(value)}</span>
  if (typeof value === 'number') return <span>{String(value)}</span>
  if (Array.isArray(value)) {
    if (value.length === 0) return <span>暂无</span>
    return <div data-gerclaw-result-list>{(value as unknown[]).map((item, index) => (
      <article key={index}><StructuredValue value={item} depth={depth + 1} /></article>
    ))}</div>
  }
  const entries = Object.entries(value as JsonObject)
    .filter(([key, item]) => !hiddenResultKeys.has(key) && item !== undefined
      && !(Array.isArray(item) && item.length === 0)
      && !(typeof item === 'object' && item !== null && !Array.isArray(item)
        && Object.keys(item as JsonObject).length === 0))
  return <dl data-gerclaw-result-data data-depth={depth}>
    {entries.map(([key, item]) => <div key={key}>
      <dt>{labels[key] ?? key}</dt>
      <dd>{key === 'url' && typeof item === 'string' && /^https?:\/\//u.test(item)
        ? <a href={item} target="_blank" rel="noreferrer">打开原文</a>
        : <StructuredValue value={item} depth={depth + 1} />}</dd>
    </div>)}
  </dl>
}

export function TaskResult({ response, sessionId, remote }: {
  response: Response
  sessionId: string
  remote: MedicalRemoteActions
}) {
  const task = response.task
  const taskId = task?.taskId
  const result = response.result ?? response.reply ?? response.item ?? response
  const [exporting, setExporting] = useState(false)
  const [exported, setExported] = useState('')
  const evidence = typeof result === 'object'
    && Array.isArray((result as JsonObject).evidenceSources)
    ? (result as JsonObject).evidenceSources as unknown[]
    : []
  return <section data-gerclaw-task-result aria-live="polite">
    {task?.steps?.map((step, index) => <div data-gerclaw-step key={`${step.name}-${index}`}>
      <i aria-hidden="true" />
      <div><strong>{step.name}</strong><span>{step.summary}</span></div>
      <time>{seconds(step.elapsedMs)}</time>
    </div>)}
    {task?.elapsedMs !== undefined && <p data-gerclaw-total>总用时：{seconds(task.elapsedMs)}</p>}
    <div data-gerclaw-final>
      <h3>最终结果</h3>
      <StructuredValue value={result} />
      {evidence.length > 0 && <details data-gerclaw-evidence>
        <summary>查看参考证据（{evidence.length} 条）</summary>
        <StructuredValue value={evidence} />
      </details>}
    </div>
    {taskId && <div data-gerclaw-form-actions>
      <button type="button" disabled={exporting} onClick={() => {
        setExporting(true)
        void remote.export(sessionId, taskId, ['md', 'html', 'docx', 'pdf', 'png', 'jpg', 'json']).then((artifacts) => {
          const count = artifacts.length
          setExported(`已生成 ${count} 个格式，右侧“产物”可预览和下载`)
        }).catch((error: unknown) => { setExported(error instanceof Error ? error.message : '导出失败') })
          .finally(() => { setExporting(false) })
      }}>{exporting ? '正在导出…' : '导出七种格式'}</button>
      {exported && <span role="status">{exported}</span>}
    </div>}
  </section>
}

function Runner({ children, submitLabel, request, sessionId, remote }: {
  children: ReactNode
  submitLabel: string
  request: (requestId: string, signal: AbortSignal) => Promise<Response>
  sessionId: string
  remote: MedicalRemoteActions
}) {
  const [running, setRunning] = useState(false)
  const [started, setStarted] = useState(0)
  const [now, setNow] = useState(0)
  const [response, setResponse] = useState<Response | null>(null)
  const [error, setError] = useState('')
  const active = useRef<{ requestId: string; controller: AbortController } | null>(null)
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => { setNow(performance.now()) }, 100)
    return () => { window.clearInterval(timer) }
  }, [running])
  const submit = (event: FormEvent): void => {
    event.preventDefault()
    const controller = new AbortController()
    const requestId = globalThis.crypto.randomUUID()
    active.current = { requestId, controller }
    setRunning(true); setStarted(performance.now()); setNow(performance.now()); setError(''); setResponse(null)
    void request(requestId, controller.signal).then(setResponse).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '操作失败')
    }).finally(() => {
      if (active.current?.requestId === requestId) active.current = null
      setRunning(false)
    })
  }
  return <form data-gerclaw-feature-form onSubmit={submit}>
    {children}
    <div data-gerclaw-form-actions>
      <button type="submit" disabled={running}>{running ? '正在处理…' : submitLabel}</button>
      {running && <button type="button" onClick={() => {
        const current = active.current
        if (current === null) return
        current.controller.abort()
        void remote.cancel(sessionId, current.requestId)
      }}>停止任务</button>}
      {running && <span role="status">正在执行 · {((now - started) / 1000).toFixed(1)} 秒</span>}
    </div>
    {error && <div data-gerclaw-error role="alert"><strong>这一步没有完成</strong><span>{error}</span></div>}
    {response && <TaskResult response={response} sessionId={sessionId} remote={remote} />}
  </form>
}

function AnswerSelect({ value, options, onChange }: {
  value: number | string
  options: CgaOption[]
  onChange: (value: number | string) => void
}) {
  return <select value={value} onChange={(event) => {
    const option = options.find(item => String(item.value) === event.target.value)
    if (option) onChange(option.value)
  }}>{options.map(option => <option key={String(option.value)} value={option.value}>{option.label}</option>)}</select>
}

function QuestionGroup({ title, children }: { title: string; children: ReactNode }) {
  return <fieldset data-gerclaw-question-group><legend>{title}</legend>{children}</fieldset>
}

function CgaForm({ sessionId, remote }: { sessionId: string; remote: MedicalRemoteActions }) {
  const [kind, setKind] = useState('phq9')
  const [answers, setAnswers] = useState<Partial<Record<string, number | string>>>({})
  useEffect(() => { setAnswers({}) }, [kind])
  const set = (key: string, value: number | string) => { setAnswers(current => ({ ...current, [key]: value })) }
  const questions = useMemo(() => {
    const renderRows = (items: readonly string[], options: CgaOption[], start = 0) => items.map((question, index) => {
      const key = `q${start + index + 1}`
      return <label key={key}>
        <span>{start + index + 1}. {question}</span>
        <AnswerSelect
          value={answers[key] ?? options[0]?.value ?? 0}
          options={options}
          onChange={(value) => { set(key, value) }}
        />
      </label>
    })
    if (kind === 'phq9') return <QuestionGroup title="过去两周内，以下情况困扰您的频率">{renderRows(phq9Questions, phq9Options)}</QuestionGroup>
    if (kind === 'sas') return <>{[0, 5, 10, 15].map(start => <QuestionGroup key={start} title={`第 ${start + 1}–${start + 5} 题`}>{renderRows(sasQuestions.slice(start, start + 5), sasOptions, start)}</QuestionGroup>)}</>
    if (kind === 'mmse') {
      let start = 0
      return <>
        <label>受教育程度<select value={String(answers.education ?? 'secondary')} onChange={(event) => { set('education', event.target.value) }}><option value="none">未受过学校教育</option><option value="primary">小学或受教育年限不超过6年</option><option value="secondary">中学或以上</option></select></label>
        {mmseGroups.map((group) => {
          const groupStart = start
          start += group.questions.length
          return <QuestionGroup key={group.title} title={group.title}>{renderRows(group.questions, mmseOptions, groupStart)}</QuestionGroup>
        })}
      </>
    }
    if (kind === 'minicog') return <>
      <QuestionGroup title="第 1 步 · 记住三个词"><p>请先记住三个词：<strong>苹果、手表、国旗</strong>。稍后会请您回忆。</p><label><span>准备好后继续</span><select aria-label="记忆准备"><option>已记住，继续</option></select></label></QuestionGroup>
      <QuestionGroup title="第 2 步 · 画钟"><p>请在纸上画一个时钟，写上 1 到 12，并把指针指向 11 点 10 分。</p><label><span>实际完成情况</span><AnswerSelect value={answers.clock ?? 0} options={[{ value: 0, label: '表盘或时间尚未完成，或我不确定' }, { value: 1, label: '数字和表盘完整，指针位置不确定' }, { value: 2, label: '数字和表盘完整，指针指向11点10分' }]} onChange={(value) => { set('clock', value) }} /></label></QuestionGroup>
      <QuestionGroup title="第 3 步 · 回忆"><p>现在请回忆刚才记住的“苹果、手表、国旗”。</p><label><span>能回忆出几个？</span><AnswerSelect value={answers.recall ?? 0} options={[0, 1, 2, 3].map(value => ({ value, label: value === 0 ? '没有回忆出来' : `回忆出${value}个` }))} onChange={(value) => { set('recall', value) }} /></label></QuestionGroup>
    </>
    return <>
      <QuestionGroup title="睡眠时间">
        <label><span>1. 过去1个月，您通常上床睡觉的时间</span><input type="time" value={String(answers.bedtime ?? '22:00')} onChange={(event) => { set('bedtime', event.target.value) }} /></label>
        <label><span>2. 过去1个月，您每晚通常要多长时间才能入睡</span><input type="number" min="0" max="1440" value={Number(answers.latencyMinutes ?? 20)} onChange={(event) => { set('latencyMinutes', Number(event.target.value)) }} /><small>请填写分钟数</small></label>
        <label><span>3. 过去1个月，您每天早上通常什么时候起床</span><input type="time" value={String(answers.waketime ?? '06:00')} onChange={(event) => { set('waketime', event.target.value) }} /></label>
        <label><span>4. 过去1个月，您每晚实际睡眠的时长</span><input type="number" min="0" max="1440" value={Number(answers.sleepMinutes ?? 420)} onChange={(event) => { set('sleepMinutes', Number(event.target.value)) }} /><small>请填写分钟数</small></label>
      </QuestionGroup>
      <QuestionGroup title="影响睡眠的情况">{psqiDisturbanceQuestions.map(([key, question], index) => <label key={key}><span>{index + 5}. {question}</span><AnswerSelect value={answers[key] ?? 0} options={psqiFrequencyOptions} onChange={(value) => { set(key, value) }} /></label>)}</QuestionGroup>
      <QuestionGroup title="总体睡眠与日间状态">
        <label><span>15. 对过去1个月睡眠质量总的评价</span><AnswerSelect value={answers.q6 ?? 0} options={psqiQualityOptions} onChange={(value) => { set('q6', value) }} /></label>
        <label><span>16. 近1个月使用催眠药物的情况</span><AnswerSelect value={answers.q7 ?? 0} options={psqiFrequencyOptions} onChange={(value) => { set('q7', value) }} /></label>
        <label><span>17. 开车、吃饭或参加社会活动时难以保持清醒</span><AnswerSelect value={answers.q8 ?? 0} options={psqiFrequencyOptions} onChange={(value) => { set('q8', value) }} /></label>
        <label><span>18. 积极完成事情有无困难</span><AnswerSelect value={answers.q9 ?? 0} options={psqiDaytimeOptions} onChange={(value) => { set('q9', value) }} /></label>
        <label><span>19. 您是与人同睡一床或有室友</span><AnswerSelect value={answers.q10 ?? 0} options={psqiPartnerOptions} onChange={(value) => { set('q10', value) }} /></label>
      </QuestionGroup>
    </>
  }, [answers, kind])
  const normalized = useMemo(() => {
    const next = { ...answers }
    if (kind === 'phq9' || kind === 'sas' || kind === 'mmse') {
      const count = kind === 'phq9' ? 9 : kind === 'sas' ? 20 : 30
      const fallback = kind === 'sas' ? 1 : 0
      for (let index = 1; index <= count; index += 1) next[`q${index}`] ??= fallback
      if (kind === 'mmse') next.education ??= 'secondary'
    } else if (kind === 'minicog') { next.clock ??= 0; next.recall ??= 0 }
    else {
      next.bedtime ??= '22:00'; next.waketime ??= '06:00'; next.latencyMinutes ??= 20; next.sleepMinutes ??= 420
      for (const key of ['q5a','q5b','q5c','q5d','q5e','q5f','q5g','q5h','q5i','q5j','q6','q7','q8','q9']) next[key] ??= 0
      next.q10 ??= 0
    }
    return Object.fromEntries(
      Object.entries(next).filter((entry): entry is [string, number | string] => entry[1] !== undefined),
    )
  }, [answers, kind])
  return <Runner sessionId={sessionId} remote={remote} submitLabel="完成确定性计分" request={async (requestId, signal) => {
    const value = await remote.submit('cga', sessionId, { kind, answers: normalized }, requestId, signal)
    return value.response as Response
  }}>
    <p data-gerclaw-intro>量表完全按固定规则计分，不调用模型。请按真实情况逐项填写。</p>
    <label>选择量表<select value={kind} onChange={(event) => { setKind(event.target.value) }}><option value="phq9">PHQ-9 抑郁筛查</option><option value="sas">SAS 焦虑自评</option><option value="psqi">PSQI 睡眠质量</option><option value="minicog">Mini-Cog 认知筛查</option><option value="mmse">MMSE 简易精神状态检查</option></select></label>
    <div data-gerclaw-question-list>{questions}</div>
  </Runner>
}

function MedicationForm({ sessionId, remote }: { sessionId: string; remote: MedicalRemoteActions }) {
  const [age, setAge] = useState('')
  const [list, setList] = useState('华法林 每日一次\n阿司匹林 每日一次')
  return <Runner sessionId={sessionId} remote={remote} submitLabel="开始核对" request={async (requestId, signal) => {
    const value = await remote.submit('medication', sessionId, { medicationList: list, ...(age ? { patientAge: Number(age) } : {}) }, requestId, signal)
    return value.response as Response
  }}>
    <p data-gerclaw-intro>按规则 v4 检查 30 条相互作用、剂量阈值、重复用药、多药联用与老年用药信号。</p>
    <label>年龄（可选）<input type="number" min="0" max="130" value={age} onChange={(event) => { setAge(event.target.value) }} /></label>
    <label>用药清单（每行一项）<textarea required value={list} onChange={(event) => { setList(event.target.value) }} /></label>
  </Runner>
}

function ProfileForm({ sessionId, remote }: { sessionId: string; remote: MedicalRemoteActions }) {
  const [values, setValues] = useState({ name: '', age: '', allergies: '', conditions: '', medications: '', goals: '' })
  useEffect(() => {
    const controller = new AbortController()
    void api(sessionId, '/bootstrap', { signal: controller.signal }).then((data) => {
      const profile = data.profile as JsonObject | undefined
      if (!profile) return
      const rows = (key: string) => Array.isArray(profile[key]) ? (profile[key] as unknown[]).join('\n') : ''
      const displayName = typeof profile.displayName === 'string' ? profile.displayName : ''
      const age = typeof profile.age === 'string' || typeof profile.age === 'number' ? String(profile.age) : ''
      setValues({
        name: displayName,
        age,
        allergies: rows('allergies'),
        conditions: rows('conditions'),
        medications: rows('medications'),
        goals: rows('goals'),
      })
    }).catch(() => {})
    return () => { controller.abort() }
  }, [sessionId])
  const field = (key: keyof typeof values, label: string, area = false) => <label>{label}{area
    ? <textarea value={values[key]} onChange={(event) => { setValues(current => ({ ...current, [key]: event.target.value })) }} />
    : <input type={key === 'age' ? 'number' : 'text'} min={key === 'age' ? 0 : undefined} max={key === 'age' ? 130 : undefined} value={values[key]} onChange={(event) => { setValues(current => ({ ...current, [key]: event.target.value })) }} />}</label>
  return <Runner sessionId={sessionId} remote={remote} submitLabel="保存健康档案" request={async (requestId, signal) => {
    const value = await remote.submit('profile', sessionId, { displayName: values.name, ...(values.age ? { age: Number(values.age) } : {}), allergies: lineList(values.allergies), conditions: lineList(values.conditions), medications: lineList(values.medications), goals: lineList(values.goals), preferences: [] }, requestId, signal)
    return value.response as Response
  }}>
    <p data-gerclaw-intro>这是处方和风险计算采用的权威结构化资料，只有当前账号可以查看和修改。</p>
    <div data-gerclaw-form-grid>{field('name', '称呼')}{field('age', '年龄')}{field('allergies', '过敏史', true)}{field('conditions', '已有疾病', true)}{field('medications', '当前用药', true)}{field('goals', '健康目标', true)}</div>
  </Runner>
}

function ChronicForm({ sessionId, remote }: { sessionId: string; remote: MedicalRemoteActions }) {
  const [values, setValues] = useState({ conditionId: '高血压管理', metricLabel: '收缩压', value: '', unit: 'mmHg' })
  const input = (key: keyof typeof values, label: string) => <label>{label}<input
    required
    value={values[key]}
    onChange={(event) => { setValues(current => ({ ...current, [key]: event.target.value })) }}
  /></label>
  return <Runner sessionId={sessionId} remote={remote} submitLabel="保存测量" request={async (requestId, signal) => {
    const value = await remote.submit('chronic', sessionId, { ...values, value: Number(values.value) }, requestId, signal)
    return value.response as Response
  }}>
    <p data-gerclaw-intro>记录测量并查看确定性趋势，不作诊断性解释。</p>
    <div data-gerclaw-form-grid>
      {input('conditionId', '管理项目')}
      {input('metricLabel', '指标')}
      {input('value', '数值')}
      {input('unit', '单位')}
    </div>
  </Runner>
}

function CompanionForm({ sessionId, remote }: { sessionId: string; remote: MedicalRemoteActions }) {
  const [text, setText] = useState('')
  return <Runner sessionId={sessionId} remote={remote} submitLabel="和我聊聊" request={async (requestId, signal) => {
    const value = await remote.submit('companion', sessionId, { text }, requestId, signal)
    return value.response as Response
  }}>
    <p data-gerclaw-intro>只根据这一次文字提供支持，不读取长期记忆、文档或知识库。</p>
    <label>
      此刻想说的话
      <textarea required value={text} onChange={(event) => { setText(event.target.value) }} />
    </label>
  </Runner>
}

function EvidenceForm({ sessionId, remote }: { sessionId: string; remote: MedicalRemoteActions }) {
  const [query, setQuery] = useState('')
  const [upload, setUpload] = useState('')
  const [documents, setDocuments] = useState<Array<{ documentId: string; name: string; size: number }>>([])
  const refreshDocuments = (): void => {
    void api(sessionId, '/bootstrap').then((value) => {
      setDocuments(Array.isArray(value.documents) ? value.documents as Array<{ documentId: string; name: string; size: number }> : [])
    }).catch(() => {})
  }
  useEffect(() => { refreshDocuments() }, [sessionId])
  const uploadFiles = async (files: FileList | null): Promise<void> => {
    if (!files?.length) return
    setUpload('正在解析并加入本账号文档库…')
    try {
      for (const file of Array.from(files)) {
        const buffer = new Uint8Array(await file.arrayBuffer())
        let binary = ''
        for (let index = 0; index < buffer.length; index += 0x8000) binary += String.fromCharCode(...buffer.subarray(index, index + 0x8000))
        await api(sessionId, '/documents', { method: 'POST', body: JSON.stringify({ name: file.name, data: btoa(binary) }) })
      }
      setUpload(`已加入 ${files.length} 份文档`)
      refreshDocuments()
    } catch (error) { setUpload(error instanceof Error ? error.message : '文档解析失败') }
  }
  return <Runner sessionId={sessionId} remote={remote} submitLabel="检索本地与医学资料" request={async (requestId, signal) => {
    const value = await remote.submit('evidence', sessionId, { query }, requestId, signal)
    return value.response as Response
  }}>
    <p data-gerclaw-intro>固定使用当前项目的本地知识库，也可检索 PubMed、openFDA 与 MedlinePlus。</p>
    <label>添加到我的文档库<input
      type="file"
      multiple
      accept=".pdf,.md,.txt,.docx"
      onChange={(event) => { void uploadFiles(event.target.files) }}
    /></label>
    {upload && <span role="status">{upload}</span>}
    {documents.length > 0 && <section data-gerclaw-documents aria-label="我的文档">
      <strong>我的文档</strong>
      <ul>{documents.map(document => <li key={document.documentId}>
        <span>{document.name}</span>
        <a href={`/gerclaw/api/documents/${encodeURIComponent(document.documentId)}`} download>下载</a>
      </li>)}</ul>
    </section>}
    <label>检索词<input required value={query} onChange={(event) => { setQuery(event.target.value) }} placeholder="例如：老年高血压睡眠管理" /></label>
  </Runner>
}

function RisksView({ sessionId }: { sessionId: string }) {
  const [data, setData] = useState<Response | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    void api(sessionId, '/bootstrap').then(setData).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : '无法读取风险提醒')
    })
  }, [sessionId])
  return <section data-gerclaw-feature-form>
    {error && <div data-gerclaw-error>{error}</div>}
    <p data-gerclaw-intro>汇总量表、用药与陪伴对话中的重要信号。</p>
    <StructuredValue value={data?.risks ?? []} />
  </section>
}

export function MedicalFeature({ feature, sessionId, remote }: { feature: FeatureId; sessionId: string; remote: MedicalRemoteActions }) {
  if (feature === 'cga') return <CgaForm sessionId={sessionId} remote={remote} />
  if (feature === 'medication') return <MedicationForm sessionId={sessionId} remote={remote} />
  if (feature === 'profile') return <ProfileForm sessionId={sessionId} remote={remote} />
  if (feature === 'chronic') return <ChronicForm sessionId={sessionId} remote={remote} />
  if (feature === 'companion') return <CompanionForm sessionId={sessionId} remote={remote} />
  if (feature === 'documents') return <EvidenceForm sessionId={sessionId} remote={remote} />
  if (feature === 'risks') return <RisksView sessionId={sessionId} />
  return null
}
