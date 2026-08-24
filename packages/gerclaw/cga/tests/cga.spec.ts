import { describe, expect, it } from 'vitest'
import { compareCgaHistory, scoreCga } from '../src/index.ts'

const answers = (count: number, value: number) => Object.fromEntries(
  Array.from({ length: count }, (_, index) => [`q${index + 1}`, value]),
)
const binaryAnswers = (score: number) => Object.fromEntries(
  Array.from({ length: 30 }, (_, index) => [`q${index + 1}`, index < score ? 1 : 0]),
)
const sasForRaw = (raw: number) => {
  const values = answers(20, 1)
  const forward = [1, 2, 3, 4, 6, 7, 8, 10, 11, 12, 14, 15, 16, 18, 20]
  let remaining = raw - 35
  for (const index of forward) {
    const add = Math.min(3, remaining)
    values[`q${index}`] = 1 + add
    remaining -= add
  }
  if (remaining !== 0) throw new Error('test raw score is outside supported range')
  return values
}
const psqi = (overrides: Record<string, number | string> = {}) => ({
  bedtime: '22:00', waketime: '06:00', sleepMinutes: 450, latencyMinutes: 10,
  q5a: 0, q5b: 0, q5c: 0, q5d: 0, q5e: 0, q5f: 0, q5g: 0,
  q5h: 0, q5i: 0, q5j: 0, q6: 0, q7: 0, q8: 0, q9: 0,
  ...overrides,
})

describe('GerClaw CGA deterministic scoring', () => {
  it.each([
    [4, '最轻微'], [5, '轻度'], [9, '轻度'], [10, '中度'], [14, '中度'],
    [15, '中重度'], [19, '中重度'], [20, '重度'], [27, '重度'],
  ])('keeps PHQ-9 boundary %i in the expected band', (score, severity) => {
    const value = answers(9, 0)
    let remaining = score
    for (let index = 1; index <= 8; index += 1) {
      const item = Math.min(3, remaining)
      value[`q${index}`] = item
      remaining -= item
    }
    value.q9 = remaining
    expect(scoreCga({ kind: 'phq9', answers: value })).toMatchObject({ score, severity })
  })

  it('raises the PHQ-9 item 9 safety result independently of total score', () => {
    expect(scoreCga({ kind: 'phq9', answers: { ...answers(9, 0), q9: 1 } }))
      .toMatchObject({ score: 1, followUp: 'immediate', safetyAlert: expect.any(String) })
  })

  it.each([
    [39, 49, '无明显焦虑'], [40, 50, '轻度'], [47, 59, '轻度'],
    [48, 60, '中度'], [55, 69, '中度'], [56, 70, '重度'],
  ])('keeps SAS raw %i rounding and severity boundaries', (raw, score, severity) => {
    expect(scoreCga({ kind: 'sas', answers: sasForRaw(raw) }))
      .toMatchObject({ score, severity })
  })

  it('scores PSQI normal, boundary and severe inputs by seven components', () => {
    expect(scoreCga({ kind: 'psqi', answers: psqi() }))
      .toMatchObject({ score: 0, severity: '睡眠质量很好' })
    expect(scoreCga({ kind: 'psqi', answers: psqi({ sleepMinutes: 420 }) }).components?.duration).toBe(1)
    expect(scoreCga({ kind: 'psqi', answers: psqi({
      sleepMinutes: 200, latencyMinutes: 120,
      q5a: 3, q5b: 3, q5c: 3, q5d: 3, q5e: 3, q5f: 3, q5g: 3,
      q5h: 3, q5i: 3, q5j: 3, q6: 3, q7: 3, q8: 3, q9: 3,
    }) })).toMatchObject({ score: 21, severity: '睡眠质量较差', followUp: 'priority' })
  })

  it('rejects missing, out-of-range and impossible PSQI answers', () => {
    expect(() => scoreCga({ kind: 'phq9', answers: answers(8, 0) })).toThrow('q9')
    expect(() => scoreCga({ kind: 'sas', answers: { ...answers(20, 1), q3: 5 } })).toThrow('q3')
    expect(() => scoreCga({ kind: 'psqi', answers: psqi({ sleepMinutes: 600 }) })).toThrow('不能超过卧床时间')
    expect(() => scoreCga({ kind: 'psqi', answers: psqi({ bedtime: '24:00' }) })).toThrow('HH:mm')
  })

  it('applies Mini-Cog and education-specific MMSE boundaries', () => {
    expect(scoreCga({ kind: 'minicog', answers: { clock: 0, recall: 2 } })).toMatchObject({ score: 2, followUp: 'priority' })
    expect(scoreCga({ kind: 'minicog', answers: { clock: 1, recall: 2 } })).toMatchObject({ score: 3, followUp: 'routine' })
    expect(scoreCga({ kind: 'mmse', answers: { education: 'none', ...binaryAnswers(17) } }).followUp).toBe('priority')
    expect(scoreCga({ kind: 'mmse', answers: { education: 'none', ...binaryAnswers(18) } }).followUp).toBe('routine')
    expect(scoreCga({ kind: 'mmse', answers: { education: 'primary', ...binaryAnswers(20) } }).followUp).toBe('priority')
    expect(scoreCga({ kind: 'mmse', answers: { education: 'secondary', ...binaryAnswers(25) } }).followUp).toBe('routine')
  })

  it('compares only the same scale and respects higher-is-better scales', () => {
    const current = scoreCga({ kind: 'phq9', answers: { ...answers(9, 0), q1: 3 } })
    expect(compareCgaHistory(current, {
      result: scoreCga({ kind: 'phq9', answers: { ...answers(9, 0), q1: 1 } }),
      completedAt: '2026-08-01T00:00:00.000Z',
    }).comparison).toEqual({
      previousScore: 1, delta: 2, direction: 'worsened',
      previousCompletedAt: '2026-08-01T00:00:00.000Z',
    })
    const minicog = scoreCga({ kind: 'minicog', answers: { clock: 2, recall: 2 } })
    expect(compareCgaHistory(minicog, {
      result: scoreCga({ kind: 'minicog', answers: { clock: 1, recall: 1 } }),
    }).comparison?.direction).toBe('improved')
    expect(compareCgaHistory(current, { result: minicog }).comparison).toBeUndefined()
  })
})
