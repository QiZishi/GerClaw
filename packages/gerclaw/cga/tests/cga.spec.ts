import { describe, expect, it } from 'vitest'
import { scoreCga } from '../src/index.ts'

describe('GerClaw CGA scoring', () => {
  it('preserves PHQ-9 boundary and item 9 safety behavior', () => {
    expect(scoreCga({ kind: 'phq9', answers: Object.fromEntries(Array.from({ length: 9 }, (_, i) => [`q${i + 1}`, i === 8 ? 1 : 2])) })).toMatchObject({ score: 17, severity: '中重度', followUp: 'immediate' })
  })
  it('uses SAS reverse scoring and round-half-up', () => {
    expect(scoreCga({ kind: 'sas', answers: Object.fromEntries(Array.from({ length: 20 }, (_, i) => [`q${i + 1}`, 1])) }).score).toBe(44)
  })
  it('applies Mini-Cog and MMSE education thresholds', () => {
    expect(scoreCga({ kind: 'minicog', answers: { clock: 1, recall: 1 } }).followUp).toBe('priority')
    expect(scoreCga({ kind: 'mmse', answers: { education: 'primary', ...Object.fromEntries(Array.from({ length: 30 }, (_, i) => [`q${i + 1}`, i < 20 ? 1 : 0])) } }).followUp).toBe('priority')
  })
})
