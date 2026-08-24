/** Evidence-bound five-prescription generation over the native DSH LLM service. */
import { Context, Service } from '@deepseek-ai/cordis'
import { BlockAssembler, createUserMessage } from '@deepseek-ai/dsh-llm'
import type { MedicationReview } from '@gerclaw/medication-review'
import type { GerclawRagHit as LocalRagHit } from '@gerclaw/library'
export interface EvidenceSource {
  evidenceId: string
  title: string
  source: string
  locator: string
  url?: string
  snippet?: string
}
export const evidenceFromLocalHits = (
  hits: readonly LocalRagHit[],
): EvidenceSource[] =>
  hits.map(hit => ({
    evidenceId: `local_${hit.chunkId.replace(/[^a-zA-Z0-9]/g, '').slice(0, 48)}`,
    title: `${hit.origin === 'user' ? '本账号资料' : '本地医学资料'} ${hit.documentId}`,
    source: hit.origin === 'user' ? '本账号文档库' : 'GerClaw 本地医学知识库',
    locator: `${hit.documentId}:${hit.seq}`,
    snippet: hit.snippet,
  }))
export interface PrescriptionRequest {
  healthGoals: string[]
  currentConcerns: string[]
  currentMedications?: string
  age?: number
  sex?: 'female' | 'male' | 'other' | 'unknown'
  documentRefs?: string[]
  evidence: EvidenceSource[]
  profileSummary?: string
}
export const MAX_PRESCRIPTION_INTAKE_TURNS = 5
export type PrescriptionIntakeField =
  | 'healthGoal'
  | 'currentConcerns'
export interface PrescriptionIntakeState {
  version: 1
  status: 'collecting' | 'information_complete' | 'limit_reached' | 'completed'
  healthGoal?: string
  currentConcerns?: string
  currentMedications?: string
  documentRefs: string[]
  conversationTurns: number
  missingFields: PrescriptionIntakeField[]
  nextQuestion?: string
  updatedAt: string
}
export interface PrescriptionIntakeUpdate {
  healthGoal?: string
  currentConcerns?: string
  currentMedications?: string
  documentRefs?: string[]
}

const boundedText = (value: string | undefined, max: number): string | undefined => {
  const normalized = value?.trim()
  if (!normalized) return undefined
  if (normalized.length > max) throw new Error(`处方资料字段不能超过 ${max} 个字符`)
  return normalized
}

export function prescriptionIntakeQuestion(
  missing: readonly PrescriptionIntakeField[],
): string | undefined {
  if (missing.includes('healthGoal'))
    return '这次您最希望改善或管理的健康目标是什么？'
  if (missing.includes('currentConcerns'))
    return '目前最困扰您的症状、问题或检查异常是什么？'
  return undefined
}

/** Advance one schema-bound intake turn without guessing or overwriting facts. */
export function advancePrescriptionIntake(
  previous: PrescriptionIntakeState | undefined,
  update: PrescriptionIntakeUpdate,
  now = new Date().toISOString(),
): PrescriptionIntakeState {
  if (previous?.status === 'completed')
    throw new Error('本次五大处方已经完成，请开始新的处方会话')
  if (previous?.status === 'limit_reached')
    throw new Error('本次资料收集已达到 5 轮，请重新开始并尽量一次提供完整资料')
  const conversationTurns = (previous?.conversationTurns ?? 0) + 1
  if (conversationTurns > MAX_PRESCRIPTION_INTAKE_TURNS)
    throw new Error('五大处方资料收集最多进行 5 轮')
  const healthGoal = previous?.healthGoal
    ?? boundedText(update.healthGoal, 500)
  const currentConcerns = previous?.currentConcerns
    ?? boundedText(update.currentConcerns, 1000)
  const currentMedications = previous?.currentMedications
    ?? boundedText(update.currentMedications, 1000)
  const documentRefs = [...new Set([
    ...(previous?.documentRefs ?? []),
    ...(update.documentRefs ?? []).map(value => value.trim()).filter(Boolean),
  ])]
  if (documentRefs.length > 10) throw new Error('一次最多使用 10 份资料')
  const missingFields: PrescriptionIntakeField[] = [
    ...(healthGoal ? [] : ['healthGoal' as const]),
    ...(currentConcerns ? [] : ['currentConcerns' as const]),
  ]
  const informationComplete = missingFields.length === 0
  const limitReached = !informationComplete
    && conversationTurns >= MAX_PRESCRIPTION_INTAKE_TURNS
  const nextQuestion = prescriptionIntakeQuestion(missingFields)
  return {
    version: 1,
    status: informationComplete
      ? 'information_complete'
      : limitReached
        ? 'limit_reached'
        : 'collecting',
    ...(healthGoal === undefined ? {} : { healthGoal }),
    ...(currentConcerns === undefined ? {} : { currentConcerns }),
    ...(currentMedications === undefined ? {} : { currentMedications }),
    documentRefs,
    conversationTurns,
    missingFields,
    ...(!informationComplete && !limitReached && nextQuestion !== undefined
      ? { nextQuestion }
      : {}),
    updatedAt: now,
  }
}

export function prescriptionRequestFromIntake(
  intake: PrescriptionIntakeState,
  evidence: EvidenceSource[] = [],
): PrescriptionRequest {
  if (intake.status !== 'information_complete')
    throw new Error('五大处方资料尚未收集完整')
  if (!intake.healthGoal || !intake.currentConcerns)
    throw new Error('五大处方缺少健康目标或当前问题')
  return {
    healthGoals: [intake.healthGoal],
    currentConcerns: [intake.currentConcerns],
    ...(intake.currentMedications === undefined
      ? {}
      : { currentMedications: intake.currentMedications }),
    documentRefs: intake.documentRefs,
    evidence,
  }
}
export interface PrescriptionRecommendation {
  content: string
  evidenceIds: string[]
}
export interface PrescriptionSection {
  kind:
    | 'medication'
    | 'exercise'
    | 'nutrition'
    | 'psychological'
    | 'rehabilitation'
  title: '药物处方' | '运动处方' | '营养处方' | '心理处方' | '康复处方'
  goal: string
  recommendations: PrescriptionRecommendation[]
  precautions: string[]
  evidenceIds: string[]
  details?: Record<string, unknown>
}
export interface PrescriptionReport {
  templateVersion: 'five-prescription-report-v1'
  modelOutputSchemaVersion: 'five-prescription-model-output-v1'
  status: 'needs_clinician_review'
  patientSummary: {
    age?: number
    sex: string
    healthGoals: string[]
    currentConcerns: string[]
  }
  healthAssessment: {
    summary: string
    keyIssues: string[]
    riskFactors: string[]
    clinicianReviewRequired: true
  }
  sections: [
    PrescriptionSection,
    PrescriptionSection,
    PrescriptionSection,
    PrescriptionSection,
    PrescriptionSection,
  ]
  medicationReview?: MedicationReview
  evidenceSources: EvidenceSource[]
  uploadedDocumentRefs: string[]
  disclaimer: string
}
export interface PrescriptionConfig {
  routes?: Array<{ provider: string; model: string }>
}
const TITLES = [
  '药物处方',
  '运动处方',
  '营养处方',
  '心理处方',
  '康复处方',
] as const
const KINDS = [
  'medication',
  'exercise',
  'nutrition',
  'psychological',
  'rehabilitation',
] as const
const SYSTEM = '你是 GerClaw 五大处方草案助手。只依据给定个人资料与证据，生成供复核的结构化草案。必须且只能按药物处方、运动处方、营养处方、心理处方、康复处方排列；睡眠内容放入心理处方。不得编造诊断、检查、来源或患者事实；“管理血压”等健康目标不等于已经诊断高血压，也不得写成既往病史。每条建议必须引用 allowedEvidenceIds 中真实存在的 evidenceId，禁止使用示例占位符或自造编号。药物调整只作为待复核候选。运动和康复必须写明循序渐进及停止条件。康复训练需有频次以及时长或强度。只输出 JSON，不要 Markdown。'
const cleanJson = (text: string): unknown => {
  const parsed: unknown[] = []
  let start = -1
  let depth = 0
  let inString = false
  let escaped = false
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (inString) {
      if (escaped) escaped = false
      else if (char === '\\') escaped = true
      else if (char === '"') inString = false
      continue
    }
    if (char === '"') {
      inString = true
      continue
    }
    if (char === '{') {
      if (depth === 0) start = index
      depth += 1
    } else if (char === '}' && depth > 0) {
      depth -= 1
      if (depth === 0 && start >= 0) {
        try {
          parsed.push(JSON.parse(text.slice(start, index + 1)))
        } catch {
          // Continue scanning: reasoning models can emit braces before final JSON.
        }
        start = -1
      }
    }
  }
  if (parsed.length === 0)
    throw new Error(
      text.includes('{')
        ? '模型返回的处方结构无法解析'
        : '模型没有返回处方结构',
    )
  return (
    parsed.findLast((value) => {
      if (typeof value !== 'object' || value === null) return false
      const candidate = value as Record<string, unknown>
      return 'healthAssessment' in candidate && Array.isArray(candidate.sections)
    }) ?? parsed.at(-1)
  )
}
const strings = (value: unknown, min = 1, max = 20): string[] => {
  if (!Array.isArray(value)) throw new Error('处方列表字段无效')
  const result = value
    .map(String)
    .map(item => item.trim())
    .filter(Boolean)
    .slice(0, max)
  if (result.length < min) throw new Error('处方列表缺少必要内容')
  return result
}
const textValue = (value: unknown): string =>
  typeof value === 'string' || typeof value === 'number'
    ? String(value).trim()
    : ''
function validateModel(
  value: unknown,
  evidence: EvidenceSource[],
): {
  healthAssessment: PrescriptionReport['healthAssessment']
  sections: PrescriptionReport['sections']
} {
  if (typeof value !== 'object' || value === null)
    throw new Error('模型返回的处方结构无效')
  const raw = value as Record<string, unknown>
  const available = new Set(evidence.map(item => item.evidenceId))
  const assessment = raw.healthAssessment as
    | Record<string, unknown>
    | undefined
  if (!assessment) throw new Error('处方缺少健康评估')
  const sourceSections = raw.sections
  if (!Array.isArray(sourceSections) || sourceSections.length !== 5)
    throw new Error('处方必须包含五个固定章节')
  const sections = sourceSections.map((entry, index) => {
    const kind = KINDS[index]
    const title = TITLES[index]
    if (!kind || !title) throw new Error('处方章节数量不正确')
    if (typeof entry !== 'object' || entry === null)
      throw new Error('处方章节无效')
    const item = entry as Record<string, unknown>
    if (item.title !== title || item.kind !== kind)
      throw new Error('处方章节名称或顺序不正确')
    const evidenceIds = strings(item.evidenceIds)
    if (evidenceIds.some(id => !available.has(id)))
      throw new Error('处方引用了不存在的证据')
    if (
      !Array.isArray(item.recommendations) ||
      item.recommendations.length === 0
    )
      throw new Error('处方章节缺少建议')
    const recommendations = item.recommendations.map((row) => {
      const rec = row as Record<string, unknown>
      const ids = strings(rec.evidenceIds)
      if (ids.some(id => !available.has(id)))
        throw new Error('处方建议引用了不存在的证据')
      return { content: textValue(rec.content), evidenceIds: ids }
    })
    if (recommendations.some(row => !row.content))
      throw new Error('处方建议内容不能为空')
    return {
      kind,
      title,
      goal: textValue(item.goal),
      recommendations,
      precautions: strings(item.precautions),
      evidenceIds,
      ...(typeof item.details === 'object' && item.details !== null
        ? { details: item.details as Record<string, unknown> }
        : {}),
    }
  }) as PrescriptionReport['sections']
  return {
    healthAssessment: {
      summary: textValue(assessment.summary),
      keyIssues: strings(assessment.keyIssues),
      riskFactors: Array.isArray(assessment.riskFactors)
        ? strings(assessment.riskFactors, 0)
        : [],
      clinicianReviewRequired: true,
    },
    sections,
  }
}
declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawPrescription: PrescriptionService
  }
}
export class PrescriptionService extends Service {
  static inject = ['llm', 'gerclawMedicationReview', 'gerclawRag']
  constructor(
    ctx: Context,
    private readonly config: PrescriptionConfig = {},
  ) {
    super(ctx, 'gerclawPrescription')
  }
  async generate(
    request: PrescriptionRequest,
    signal?: AbortSignal,
    onRoute?: (route: string) => void,
  ): Promise<PrescriptionReport> {
    if (
      request.healthGoals.length === 0 ||
      request.currentConcerns.length === 0
    )
      throw new Error('请填写健康目标和当前问题')
    if ((request.documentRefs?.length ?? 0) > 10)
      throw new Error('一次最多使用 10 份资料')
    const suppliedLocal = request.evidence.filter(
      item => item.source === 'GerClaw 本地医学知识库',
    )
    const localEvidence = suppliedLocal.length > 0
      ? suppliedLocal
      : evidenceFromLocalHits(
        await this.ctx.gerclawRag.search(
          [...request.healthGoals, ...request.currentConcerns].join(' '),
          8,
        ),
      )
    const evidence = [
      ...localEvidence,
      ...request.evidence.filter(
        item => !localEvidence.some(local => local.evidenceId === item.evidenceId),
      ),
    ]
    if (evidence.length === 0)
      throw new Error('本地知识库与权威医学源均未检索到可引用证据')
    const primaryEvidenceId = evidence[0]?.evidenceId
    if (!primaryEvidenceId) throw new Error('证据编号无效')
    const routes = this.config.routes ?? []
    if (routes.length === 0)
      throw new Error('缺少环境变量：AGENT_PRIMARY_MODEL')
    const prompt = JSON.stringify({
      allowedEvidenceIds: evidence.map(item => item.evidenceId),
      schema: {
        healthAssessment: {
          summary: 'string',
          keyIssues: ['string'],
          riskFactors: ['string'],
        },
        sections: TITLES.map((title, index) => ({
          kind: KINDS[index],
          title,
          goal: 'string',
          recommendations: [
            { content: 'string', evidenceIds: [primaryEvidenceId] },
          ],
          precautions: ['string'],
          evidenceIds: [primaryEvidenceId],
          details: {},
        })),
      },
      patient: {
        healthGoals: request.healthGoals,
        currentConcerns: request.currentConcerns,
        currentMedications: request.currentMedications ?? '',
        age: request.age ?? null,
        sex: request.sex ?? 'unknown',
        profileSummary: request.profileSummary ?? '',
        documentRefs: request.documentRefs ?? [],
      },
      evidence,
    })
    const route = routes[0]
    if (!route) throw new Error('缺少环境变量：AGENT_PRIMARY_MODEL')
    try {
      onRoute?.(`${route.provider}/${route.model}`)
      let parsed: ReturnType<typeof validateModel> | undefined
      let validationError = ''
      for (let attempt = 0; attempt < 2; attempt += 1) {
        const assembler = new BlockAssembler()
        const requestPrompt = attempt === 0
          ? prompt
          : JSON.stringify({
            correction: `上一次输出未通过结构校验：${validationError}。重新生成完整 JSON，不要解释。`,
            request: JSON.parse(prompt) as unknown,
          })
        for await (const chunk of this.ctx.llm.stream({
          provider: route.provider,
          model: route.model,
          messages: [
            createUserMessage({
              content: [{ type: 'text', text: requestPrompt }],
              source: { kind: 'user' },
            }),
          ],
          system: SYSTEM,
          // Reasoning-capable primary models account their analysis against the
          // output budget before emitting the schema-bound final JSON. The five
          // sections and their citations need materially more headroom than an
          // ordinary chat reply.
          maxTokens: 8000,
          temperature: attempt === 0 ? 0.2 : 0,
          ...(signal === undefined ? {} : { signal }),
        }))
          assembler.push(chunk)
        if (assembler.finish.kind === 'max-tokens')
          validationError = '模型输出达到长度上限，未完成处方结构'
        else if (assembler.finish.kind !== 'stop') {
          this.ctx.logger.warn(
            `gerclaw-prescription: generation ended with ${assembler.finish.kind}`,
          )
          validationError = '模型生成未完成'
        } else {
          const text = assembler
            .blocks()
            .filter(block => block.type === 'text')
            .map(block => block.text)
            .join('')
          try {
            parsed = validateModel(cleanJson(text), evidence)
            break
          } catch (error) {
            validationError = error instanceof Error ? error.message : '处方结构无效'
          }
        }
      }
      if (parsed === undefined)
        throw new Error(`模型两次输出均未通过格式校验：${validationError}`)
      const medicationReview = request.currentMedications?.trim()
        ? this.ctx.gerclawMedicationReview.review({
          medicationList: request.currentMedications,
          ...(request.age === undefined ? {} : { patientAge: request.age }),
        })
        : undefined
      return {
        templateVersion: 'five-prescription-report-v1',
        modelOutputSchemaVersion: 'five-prescription-model-output-v1',
        status: 'needs_clinician_review',
        patientSummary: {
          ...(request.age === undefined ? {} : { age: request.age }),
          sex: request.sex ?? 'unknown',
          healthGoals: request.healthGoals,
          currentConcerns: request.currentConcerns,
        },
        healthAssessment: parsed.healthAssessment,
        sections: parsed.sections,
        ...(medicationReview === undefined ? {} : { medicationReview }),
        evidenceSources: evidence,
        uploadedDocumentRefs: request.documentRefs ?? [],
        disclaimer:
            'AI生成建议仅供参考，不能替代专业医生诊断、治疗建议或处方；如有不适请及时就医。',
      }
    } catch (error) {
      if (signal?.aborted) throw error
      throw new Error(
        `模型生成失败：${error instanceof Error ? error.message : '服务不可用'}`,
      )
    }
  }
}
export default PrescriptionService
