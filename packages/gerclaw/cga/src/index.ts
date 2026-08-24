/** Deterministic GerClaw comprehensive geriatric assessment service. */
import { Context, Service } from '@deepseek-ai/cordis'

export const CGA_VERSION = '2026-07-16'
export type CgaKind = 'phq9' | 'sas' | 'psqi' | 'minicog' | 'mmse'
export interface CgaAssessment {
  kind: CgaKind
  answers: Record<string, number | string>
  completedAt?: string
}
export interface CgaResult {
  kind: CgaKind
  version: typeof CGA_VERSION
  score: number
  severity: string
  components?: Record<string, number>
  safetyAlert?: string
  followUp: 'routine' | 'priority' | 'immediate'
  comparison?: CgaComparison
  disclaimer: string
}
export interface CgaComparison {
  previousScore: number
  delta: number
  direction: 'improved' | 'worsened' | 'unchanged'
  previousCompletedAt?: string
}

const DISCLAIMER =
  '量表结果仅用于健康筛查，不能替代医生诊断；如有明显不适或危险想法，请及时寻求专业帮助。'
const numeric = (
  answers: CgaAssessment['answers'],
  key: string,
  min: number,
  max: number,
): number => {
  const value = answers[key]
  if (
    typeof value !== 'number' ||
    !Number.isFinite(value) ||
    value < min ||
    value > max
  ) {
    throw new Error(`答案 ${key} 必须是 ${min} 到 ${max} 之间的数字`)
  }
  return value
}
const all = (
  a: CgaAssessment['answers'],
  prefix: string,
  count: number,
  min: number,
  max: number,
) =>
  Array.from({ length: count }, (_, index) =>
    numeric(a, `${prefix}${index + 1}`, min, max),
  )

const assertKeys = (
  answers: CgaAssessment['answers'],
  required: readonly string[],
  optional: readonly string[] = [],
) => {
  const allowed = new Set([...required, ...optional])
  const missing = required.filter(key => !(key in answers))
  const unexpected = Object.keys(answers).filter(key => !allowed.has(key))
  if (missing.length > 0 || unexpected.length > 0)
    throw new Error(
      `答案字段不完整或包含未知字段${missing.length ? `；缺少 ${missing.join('、')}` : ''}${unexpected.length ? `；未知 ${unexpected.join('、')}` : ''}`,
    )
}
const band = (value: number, limits: readonly [number, number, number]) =>
  value <= limits[0] ? 0 : value <= limits[1] ? 1 : value <= limits[2] ? 2 : 3
const timeMinutes = (value: unknown, key: string): number => {
  if (typeof value !== 'string' || !/^([01]\d|2[0-3]):[0-5]\d$/.test(value))
    throw new Error(`${key} 必须为 HH:mm`)
  const [hour = 0, minute = 0] = value.split(':').map(Number)
  return hour * 60 + minute
}

export function scoreCga(input: CgaAssessment): CgaResult {
  if (!['phq9', 'sas', 'psqi', 'minicog', 'mmse'].includes(input.kind))
    throw new Error('不支持的量表类型')
  const base = {
    kind: input.kind,
    version: CGA_VERSION,
    disclaimer: DISCLAIMER,
  } as const
  if (input.kind === 'phq9') {
    assertKeys(input.answers, Array.from({ length: 9 }, (_, index) => `q${index + 1}`))
    const values = all(input.answers, 'q', 9, 0, 3)
    const score = values.reduce((sum, value) => sum + value, 0)
    const severity =
      score <= 4
        ? '最轻微'
        : score <= 9
          ? '轻度'
          : score <= 14
            ? '中度'
            : score <= 19
              ? '中重度'
              : '重度'
    const safetyAlert =
      (values[8] ?? 0) >= 1
        ? '您报告了伤害自己或不如死去的想法。请立即联系身边可信任的人、当地急救或心理危机干预服务，不要独自承担。'
        : undefined
    return {
      ...base,
      score,
      severity,
      ...(safetyAlert === undefined ? {} : { safetyAlert }),
      followUp: safetyAlert
        ? 'immediate'
        : score >= 20
          ? 'priority'
          : 'routine',
    }
  }
  if (input.kind === 'sas') {
    assertKeys(input.answers, Array.from({ length: 20 }, (_, index) => `q${index + 1}`))
    const values = all(input.answers, 'q', 20, 1, 4)
    const reverse = new Set([5, 9, 13, 17, 19])
    const raw = values.reduce(
      (sum, value, index) => sum + (reverse.has(index + 1) ? 5 - value : value),
      0,
    )
    const score = Math.floor(raw * 1.25 + 0.5)
    const severity =
      score < 50
        ? '无明显焦虑'
        : score < 60
          ? '轻度'
          : score < 70
            ? '中度'
            : '重度'
    return {
      ...base,
      score,
      severity,
      followUp: score >= 70 ? 'priority' : 'routine',
    }
  }
  if (input.kind === 'minicog') {
    assertKeys(input.answers, ['clock', 'recall'])
    const clock = numeric(input.answers, 'clock', 0, 2)
    const recall = numeric(input.answers, 'recall', 0, 3)
    const score = clock + recall
    return {
      ...base,
      score,
      severity: score <= 2 ? '可能存在认知功能受损' : '筛查阴性',
      followUp: score <= 2 ? 'priority' : 'routine',
    }
  }
  if (input.kind === 'mmse') {
    assertKeys(
      input.answers,
      ['education', ...Array.from({ length: 30 }, (_, index) => `q${index + 1}`)],
    )
    const values = all(input.answers, 'q', 30, 0, 1)
    const education = input.answers.education
    if (
      education !== 'none' &&
      education !== 'primary' &&
      education !== 'secondary'
    )
      throw new Error('请选择受教育程度')
    const threshold =
      education === 'none' ? 17 : education === 'primary' ? 20 : 24
    const score = values.reduce((sum, value) => sum + value, 0)
    const severity =
      score >= 27
        ? '正常'
        : score >= 21
          ? '轻度'
          : score >= 10
            ? '中度'
            : '重度'
    return {
      ...base,
      score,
      severity,
      followUp: score <= threshold ? 'priority' : 'routine',
    }
  }
  const q = input.answers
  assertKeys(
    q,
    [
      'bedtime', 'waketime', 'sleepMinutes', 'latencyMinutes',
      ...Array.from({ length: 10 }, (_, index) => `q5${String.fromCharCode(97 + index)}`),
      'q6', 'q7', 'q8', 'q9',
    ],
    ['q10'],
  )
  const bed = timeMinutes(q.bedtime, '上床时间')
  const wake = timeMinutes(q.waketime, '起床时间')
  const timeInBed = (wake - bed + 1440) % 1440
  if (timeInBed === 0) throw new Error('上床与起床时间不能相同')
  const sleepMinutes = numeric(q, 'sleepMinutes', 1, 1440)
  if (sleepMinutes > timeInBed) throw new Error('实际睡眠时间不能超过卧床时间')
  const latencyMinutes = numeric(q, 'latencyMinutes', 0, 1440)
  const sleepQuality = numeric(q, 'q6', 0, 3)
  const latency = band(
    (latencyMinutes <= 15
      ? 0
      : latencyMinutes <= 30
        ? 1
        : latencyMinutes <= 60
          ? 2
          : 3) + numeric(q, 'q5a', 0, 3),
    [0, 2, 4],
  )
  const duration =
    sleepMinutes > 420
      ? 0
      : sleepMinutes > 360
        ? 1
        : sleepMinutes >= 300
          ? 2
          : 3
  const efficiencyValue = (sleepMinutes / timeInBed) * 100
  const efficiency =
    efficiencyValue > 85
      ? 0
      : efficiencyValue >= 75
        ? 1
        : efficiencyValue >= 65
          ? 2
          : 3
  const disturbance = band(
    Array.from({ length: 9 }, (_, index) =>
      numeric(q, `q5${String.fromCharCode(98 + index)}`, 0, 3),
    ).reduce((a, b) => a + b, 0),
    [0, 9, 18],
  )
  const hypnotic = numeric(q, 'q7', 0, 3)
  const daytime = band(
    numeric(q, 'q8', 0, 3) + numeric(q, 'q9', 0, 3),
    [0, 2, 4],
  )
  const components = {
    sleepQuality,
    latency,
    duration,
    efficiency,
    disturbance,
    hypnotic,
    daytime,
  }
  const score = Object.values(components).reduce(
    (sum, value) => sum + value,
    0,
  )
  return {
    ...base,
    score,
    components,
    severity:
      score <= 5
        ? '睡眠质量很好'
        : score <= 10
          ? '睡眠质量尚可'
          : score <= 15
            ? '睡眠质量一般'
            : '睡眠质量较差',
    followUp: score >= 16 ? 'priority' : 'routine',
  }
}

/** Attach a deterministic same-scale comparison without changing scoring. */
export function compareCgaHistory(
  current: CgaResult,
  previous?: { result: CgaResult; completedAt?: string },
): CgaResult {
  if (previous === undefined || previous.result.kind !== current.kind) return current
  const delta = current.score - previous.result.score
  const higherIsBetter = current.kind === 'minicog' || current.kind === 'mmse'
  const direction = delta === 0
    ? 'unchanged'
    : (higherIsBetter ? delta > 0 : delta < 0)
      ? 'improved'
      : 'worsened'
  return {
    ...current,
    comparison: {
      previousScore: previous.result.score,
      delta,
      direction,
      ...(previous.completedAt === undefined
        ? {}
        : { previousCompletedAt: previous.completedAt }),
    },
  }
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawCga: CgaService
  }
}
export class CgaService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'gerclawCga')
  }
  score(input: CgaAssessment): CgaResult {
    return scoreCga(input)
  }
  compare(
    current: CgaResult,
    previous?: { result: CgaResult; completedAt?: string },
  ): CgaResult {
    return compareCgaHistory(current, previous)
  }
}
export default CgaService
