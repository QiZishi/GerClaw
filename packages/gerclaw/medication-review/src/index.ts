/** Source-traceable deterministic medication review ported from GerClaw rules v4. */
import { readFileSync } from 'node:fs'
import { Context, Service } from '@deepseek-ai/cordis'

export type MedicationRiskLevel =
  | 'contraindicated'
  | 'major'
  | 'moderate'
  | 'minor'
export interface MedicationReviewRequest {
  medicationList: string
  patientAge?: number
}
export interface MedicationFinding {
  findingId: string
  kind: 'ddi' | 'dose' | 'beers' | 'duplicate' | 'polypharmacy'
  severity: MedicationRiskLevel
  title: string
  involvedGenericNames: string[]
  conclusion: string
  clinicianAction: string
  elderlyNote?: string
  sourceIds: string[]
  ageEscalated: boolean
}
export interface MedicationReview {
  rulesetVersion: string
  patientAge?: number
  reviewedMedications: {
    position: number
    text: string
    recognizedGenericNames: string[]
  }[]
  findings: MedicationFinding[]
  sources: RuleSource[]
  coverage: {
    ddi: 'limited_source_traceable'
    dose: 'limited_source_traceable'
    beers: 'limited_source_traceable'
  }
  unrecognizedEntryCount: number
  conclusion: string
  disclaimer: string
}
interface RuleSource {
  source_id: string
  title: string
  publisher: string
  locator: string
  local_corpus_path: string
  content_sha256: string
  review_status: string
}
interface DdiRule {
  id: string
  drugs: [string, string]
  severity: MedicationRiskLevel
  conclusion: string
  clinician_action: string
  elderly_note?: string
  source_ids: string[]
}
interface DoseRule {
  id: string
  drug: string
  max_daily_mg: number
  severity: MedicationRiskLevel
  conclusion: string
  clinician_action: string
  elderly_note?: string
  source_ids: string[]
}
interface BeersRule {
  id: string
  drugs: string[]
  minimum_age: number
  severity: MedicationRiskLevel
  conclusion: string
  clinician_action: string
  elderly_note?: string
  source_ids: string[]
}
interface RuleSet {
  version: string
  sources: RuleSource[]
  aliases: Record<string, string[]>
  ddi_rules: DdiRule[]
  dose_rules: DoseRule[]
  beers_rules: BeersRule[]
}
const RULES = JSON.parse(
  readFileSync(new URL('../rules/core-v1.json', import.meta.url), 'utf8'),
) as RuleSet
const rank: Record<MedicationRiskLevel, number> = {
  contraindicated: 0,
  major: 1,
  moderate: 2,
  minor: 3,
}
const labels: Record<MedicationRiskLevel, string> = {
  contraindicated: '禁忌',
  major: '严重',
  moderate: '中等',
  minor: '轻微',
}
const normalize = (value: string) =>
  value.normalize('NFKC').toLocaleLowerCase().replace(/\s/g, '')
const splitEntries = (value: string) =>
  value
    .normalize('NFKC')
    .replace(/\r\n?/g, '\n')
    .split(/[\n；;]/)
    .map(row => row.trim().replace(/\s+/g, ' '))
    .filter(Boolean)
const ageAdjust = (
  severity: MedicationRiskLevel,
  age: number | undefined,
): [MedicationRiskLevel, boolean] =>
  age !== undefined && age >= 75 && severity === 'moderate'
    ? ['major', true]
    : [severity, false]
const action = (value: string) =>
  value.replace(/[；，]患者不要自行[^。]*。?/g, '。')

export function reviewMedication(
  request: MedicationReviewRequest,
): MedicationReview {
  if (
    request.patientAge !== undefined &&
    (!Number.isInteger(request.patientAge) ||
      request.patientAge < 0 ||
      request.patientAge > 130)
  )
    throw new Error('年龄必须为 0 到 130 的整数')
  const entries = splitEntries(request.medicationList)
  if (entries.length === 0) throw new Error('请填写当前用药')
  if (entries.length > 50) throw new Error('一次最多核对 50 条药物记录')
  const names = entries.map(text =>
    Object.entries(RULES.aliases)
      .filter(([, aliases]) =>
        aliases.some(alias => normalize(text).includes(normalize(alias))),
      )
      .map(([generic]) => generic),
  )
  const present = new Set(names.flat())
  const findings: MedicationFinding[] = []
  for (const rule of RULES.ddi_rules) {
    if (!rule.drugs.every(drug => present.has(drug))) continue
    const [severity, ageEscalated] = ageAdjust(
      rule.severity,
      request.patientAge,
    )
    findings.push({
      findingId: rule.id,
      kind: 'ddi',
      severity,
      title: `${rule.drugs[0]} + ${rule.drugs[1]}：${labels[severity]}风险`,
      involvedGenericNames: [...rule.drugs],
      conclusion: rule.conclusion,
      clinicianAction: action(rule.clinician_action),
      ...(rule.elderly_note === undefined
        ? {}
        : { elderlyNote: rule.elderly_note }),
      sourceIds: rule.source_ids,
      ageEscalated,
    })
  }
  for (const [index, text] of entries.entries()) {
    if (
      !/(?:每日|每天|一日)\s*一?次|(?:^|[^0-9])1\s*次\s*\/\s*(?:日|d)(?:$|[^a-z])|\bqd\b|once\s+daily/i.test(
        text,
      )
    )
      continue
    const matches = [
      ...text
        .normalize('NFKC')
        .matchAll(/(?<![0-9.])(\d+(?:\.\d+)?)\s*(?:mg|毫克)/gi),
    ]
    if (matches.length !== 1) continue
    const dailyMg = Number(matches[0]?.[1])
    for (const rule of RULES.dose_rules) {
      if (!names[index]?.includes(rule.drug) || dailyMg <= rule.max_daily_mg)
        continue
      const [severity, ageEscalated] = ageAdjust(
        rule.severity,
        request.patientAge,
      )
      findings.push({
        findingId: `${rule.id}_${index + 1}`,
        kind: 'dose',
        severity,
        title: `${rule.drug}：录入日剂量 ${dailyMg} mg 超出规则阈值`,
        involvedGenericNames: [rule.drug],
        conclusion: rule.conclusion,
        clinicianAction: action(rule.clinician_action),
        ...(rule.elderly_note === undefined
          ? {}
          : { elderlyNote: rule.elderly_note }),
        sourceIds: rule.source_ids,
        ageEscalated,
      })
    }
  }
  const positions = new Map<string, number[]>()
  names.forEach((items, index) => {
    items.forEach((name) => {
      positions.set(name, [...(positions.get(name) ?? []), index + 1])
    })
  })
  let duplicateIndex = 0
  for (const [generic, found] of positions)
    if (found.length > 1)
      findings.push({
        findingId: `duplicate_generic_${++duplicateIndex}`,
        kind: 'duplicate',
        severity: 'moderate',
        title: `${generic}：在多条录入中被识别`,
        involvedGenericNames: [generic],
        conclusion: `${generic}在第${found.join('、')}条中均被识别，需要核对是否为重复记录或重复用药。`,
        clinicianAction:
          '请由医师或药师核对每条药物的实际名称、剂型、用法和开方来源。',
        elderlyNote: '老年人多重用药时，应进行完整的药物核对。',
        sourceIds: [],
        ageEscalated: false,
      })
  for (const rule of RULES.beers_rules) {
    if (
      request.patientAge === undefined ||
      request.patientAge < rule.minimum_age
    )
      continue
    const matched = rule.drugs.filter(drug => present.has(drug))
    if (matched.length === 0) continue
    findings.push({
      findingId: rule.id,
      kind: 'beers',
      severity: rule.severity,
      title: `≥${rule.minimum_age} 岁：${matched.join('、')} 老年用药核对提示`,
      involvedGenericNames: matched,
      conclusion: rule.conclusion,
      clinicianAction: action(rule.clinician_action),
      ...(rule.elderly_note === undefined
        ? {}
        : { elderlyNote: rule.elderly_note }),
      sourceIds: rule.source_ids,
      ageEscalated: false,
    })
  }
  if (entries.length >= 5)
    findings.push({
      findingId:
        entries.length >= 10
          ? 'polypharmacy_10_or_more'
          : 'polypharmacy_5_to_9',
      kind: 'polypharmacy',
      severity: entries.length >= 10 ? 'major' : 'moderate',
      title: `已录入 ${entries.length} 种药物：多重用药核对提醒`,
      involvedGenericNames: ['多重用药'],
      conclusion:
        entries.length >= 10
          ? '已达到10种及以上药物的多重用药警示阈值。'
          : '已达到5种及以上药物的多重用药提醒阈值。',
      clinicianAction:
        '请由医师或药师进行完整的药物核对、适应证和不良反应评估。',
      elderlyNote: '老年人多重用药时，药物相互作用和不良反应风险可能增加。',
      sourceIds: [],
      ageEscalated: false,
    })
  findings.sort(
    (a, b) =>
      rank[a.severity] - rank[b.severity] ||
      a.findingId.localeCompare(b.findingId),
  )
  return {
    rulesetVersion: RULES.version,
    ...(request.patientAge === undefined
      ? {}
      : { patientAge: request.patientAge }),
    reviewedMedications: entries.map((text, index) => ({
      position: index + 1,
      text,
      recognizedGenericNames: names[index] ?? [],
    })),
    findings,
    sources: RULES.sources,
    coverage: {
      ddi: 'limited_source_traceable',
      dose: 'limited_source_traceable',
      beers: 'limited_source_traceable',
    },
    unrecognizedEntryCount: names.filter(item => item.length === 0).length,
    conclusion:
      findings.length === 0
        ? '在当前已安装的有限 DDI、剂量和 Beers 相关规则中未命中风险；这不代表用药方案安全或已完成完整 Beers 筛查。请由医师或药师完成完整核对。'
        : `本次依据已安装规则命中 ${findings.length} 项问题，最高等级为${labels[findings[0]?.severity ?? 'moderate']}。所有结论均需由医师或药师结合病情、检验和原始处方复核。`,
    disclaimer:
      '本审查仅基于已安装且来源可追溯的有限规则，不能替代医师或药师的完整用药核对；涉及开始、停用或调整剂量时，应结合完整临床资料和相应证据复核。',
  }
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawMedicationReview: MedicationReviewService
  }
}
export class MedicationReviewService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'gerclawMedicationReview')
  }
  review(request: MedicationReviewRequest): MedicationReview {
    return reviewMedication(request)
  }
}
export default MedicationReviewService
