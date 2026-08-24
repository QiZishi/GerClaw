import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { reviewMedication } from '../src/index.ts'

interface RulesFixture {
  aliases: Record<string, string[]>
  ddi_rules: { id: string; drugs: [string, string] }[]
  dose_rules: { id: string; drug: string; max_daily_mg: number }[]
}

const rules = JSON.parse(
  readFileSync(new URL('../rules/core-v1.json', import.meta.url), 'utf8'),
) as RulesFixture
const alias = (generic: string) => rules.aliases[generic]?.[0] ?? generic

describe('medication rules v4', () => {
  it('executes every one of the 30 source-traceable DDI rules', () => {
    expect(rules.ddi_rules).toHaveLength(30)
    for (const rule of rules.ddi_rules) {
      const report = reviewMedication({
        medicationList: rule.drugs.map(alias).join('；'),
        patientAge: 64,
      })
      expect(report.findings.map(item => item.findingId), rule.id).toContain(rule.id)
    }
  })

  it.each(rules.dose_rules)(
    'enforces $id only above its exact daily threshold',
    (rule) => {
      const atLimit = reviewMedication({
        medicationList: `${alias(rule.drug)} ${rule.max_daily_mg}mg 每日一次`,
        patientAge: 64,
      })
      const overLimit = reviewMedication({
        medicationList: `${alias(rule.drug)} ${rule.max_daily_mg + 1}mg 每日一次`,
        patientAge: 64,
      })
      expect(atLimit.findings.some(item => item.findingId.startsWith(rule.id))).toBe(false)
      expect(overLimit.findings.some(item => item.findingId.startsWith(rule.id))).toBe(true)
    },
  )

  it('preserves source traceability and returns all four exact dose thresholds', () => {
    for (const rule of rules.dose_rules) {
      const report = reviewMedication({ medicationList: `${alias(rule.drug)} ${rule.max_daily_mg + 1}mg 每日一次` })
      const finding = report.findings.find(item => item.findingId.startsWith(rule.id))
      expect(finding, rule.id).toBeDefined()
      expect(finding?.sourceIds.length, rule.id).toBeGreaterThan(0)
      expect(finding?.conclusion, rule.id).toContain('剂量')
    }
  })

  it('escalates moderate findings at age 75 but not age 74', () => {
    const medicationList = '左旋氨氯地平 6mg 每日一次'
    const age74 = reviewMedication({ medicationList, patientAge: 74 })
    const age75 = reviewMedication({ medicationList, patientAge: 75 })
    const finding74 = age74.findings.find(item => item.kind === 'dose')
    const finding75 = age75.findings.find(item => item.kind === 'dose')
    expect(finding74).toMatchObject({ severity: 'moderate', ageEscalated: false })
    expect(finding75).toMatchObject({ severity: 'major', ageEscalated: true })
  })

  it('applies the limited Beers signal at age 65, not age 64', () => {
    const medicationList = '地西泮 2mg 每晚一次'
    expect(reviewMedication({ medicationList, patientAge: 64 }).findings.some(item => item.kind === 'beers')).toBe(false)
    expect(reviewMedication({ medicationList, patientAge: 65 }).findings.some(item => item.kind === 'beers')).toBe(true)
  })

  it('detects generic duplicates and both polypharmacy thresholds', () => {
    const duplicate = reviewMedication({
      medicationList: '阿托伐他汀 10mg 每日一次；atorvastatin 10mg qd',
    })
    expect(duplicate.findings.some(item => item.kind === 'duplicate')).toBe(true)
    const five = reviewMedication({ medicationList: '甲；乙；丙；丁；戊' })
    const ten = reviewMedication({ medicationList: '甲；乙；丙；丁；戊；己；庚；辛；壬；癸' })
    expect(five.findings.find(item => item.kind === 'polypharmacy')).toMatchObject({
      findingId: 'polypharmacy_5_to_9', severity: 'moderate',
    })
    expect(ten.findings.find(item => item.kind === 'polypharmacy')).toMatchObject({
      findingId: 'polypharmacy_10_or_more', severity: 'major',
    })
  })

  it('detects multi-generic entries and preserves highest severity ordering', () => {
    const report = reviewMedication({
      medicationList: '瑞舒伐他汀；环孢素；地西泮；阿托伐他汀；氯吡格雷',
      patientAge: 75,
    })
    expect(report.findings.length).toBeGreaterThan(1)
    expect(report.findings[0]?.severity).toBe('contraindicated')
    expect(report.sources.every(source => source.content_sha256.length === 64)).toBe(true)
  })

  it('reports unrecognized entries without claiming complete safety', () => {
    const report = reviewMedication({ medicationList: '未收录药物甲；未收录药物乙' })
    expect(report.unrecognizedEntryCount).toBe(2)
    expect(report.conclusion).toContain('有限')
    expect(report.disclaimer).toContain('不能替代')
  })

  it.each([-1, 1.5, 131])('rejects invalid age %s', (patientAge) => {
    expect(() => reviewMedication({ medicationList: '阿司匹林', patientAge })).toThrow('年龄')
  })

  it('rejects empty input and more than 50 entries', () => {
    expect(() => reviewMedication({ medicationList: '  ' })).toThrow('当前用药')
    expect(() => reviewMedication({ medicationList: Array.from({ length: 51 }, (_, index) => `药物${index}`).join('；') })).toThrow('50')
  })
})
