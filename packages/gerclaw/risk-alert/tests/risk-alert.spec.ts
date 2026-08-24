import { describe, expect, it } from 'vitest'
import { deriveRiskAlerts } from '../src/index.ts'

describe('风险提醒确定性聚合', () => {
  it('同时聚合量表、禁忌/严重用药和陪伴紧急信号', () => {
    const alerts = deriveRiskAlerts({
      cga: { followUp: 'priority' },
      medication: { findings: [
        { findingId: 'ddi_1', severity: 'contraindicated' },
        { findingId: 'dose_1', severity: 'major' },
        { findingId: 'minor_1', severity: 'minor' },
      ] },
      companion: { urgent: true },
    })
    expect(alerts).toHaveLength(4)
    expect(alerts.map(alert => `${alert.source}:${alert.severity}`)).toEqual([
      'cga:high', 'medication_review:critical', 'medication_review:high', 'chat:critical',
    ])
    expect(alerts.every(alert => alert.status === 'active' && alert.createdAt.length > 0)).toBe(true)
  })

  it('CGA safetyAlert 优先于普通随访提醒', () => {
    const alerts = deriveRiskAlerts({ cga: { followUp: 'priority', safetyAlert: '有自伤想法' } })
    expect(alerts).toHaveLength(1)
    expect(alerts[0]).toMatchObject({ source: 'cga', severity: 'critical', alertId: 'cga_immediate' })
  })

  it('无风险输入不产生提醒，普通/中等级别用药不升级', () => {
    expect(deriveRiskAlerts({ medication: { findings: [
      { findingId: 'moderate', severity: 'moderate' },
      { findingId: 'minor', severity: 'minor' },
    ] } })).toEqual([])
  })
})
