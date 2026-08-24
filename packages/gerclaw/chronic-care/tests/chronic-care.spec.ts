import { describe, expect, it } from 'vitest'
import { calculateTrends } from '../src/index.ts'

const measurement = (
  conditionId: string,
  metricLabel: string,
  value: number,
  measuredAt: string,
  unit = 'mmHg',
) => ({
  measurementId: `${conditionId}-${metricLabel}-${measuredAt}`,
  conditionId,
  metricLabel,
  value,
  unit,
  measuredAt,
  createdAt: measuredAt,
})

describe('慢病测量确定性趋势', () => {
  it('按疾病、指标和单位分组，并给出首次/上升/下降/不变', () => {
    const result = calculateTrends([
      measurement('hypertension', '收缩压', 130, '2026-08-01T08:00:00Z'),
      measurement('hypertension', '收缩压', 140, '2026-08-02T08:00:00Z'),
      measurement('hypertension', '舒张压', 80, '2026-08-02T08:00:00Z'),
      measurement('diabetes', '收缩压', 120, '2026-08-02T08:00:00Z'),
      measurement('hypertension', '心率', 70, '2026-08-02T08:00:00Z', 'bpm'),
      measurement('hypertension', '心率', 70, '2026-08-03T08:00:00Z', 'bpm'),
    ])
    expect(result).toEqual(expect.arrayContaining([
      expect.objectContaining({ conditionId: 'hypertension', metricLabel: '收缩压', direction: 'up', previousValue: 130, latestValue: 140 }),
      expect.objectContaining({ conditionId: 'hypertension', metricLabel: '舒张压', direction: 'first' }),
      expect.objectContaining({ conditionId: 'diabetes', metricLabel: '收缩压', direction: 'first' }),
      expect.objectContaining({ conditionId: 'hypertension', metricLabel: '心率', direction: 'unchanged' }),
    ]))
    expect(result).toHaveLength(4)
  })

  it('按时间排序，不修改输入，并允许跨午夜记录', () => {
    const input = [
      measurement('copd', '血氧', 94, '2026-08-03T08:00:00Z', '%'),
      measurement('copd', '血氧', 96, '2026-08-01T08:00:00Z', '%'),
    ]
    const before = input.map(item => item.measuredAt)
    expect(calculateTrends(input)[0]).toMatchObject({ direction: 'down', previousValue: 96, latestValue: 94 })
    expect(input.map(item => item.measuredAt)).toEqual(before)
  })

  it.each([Number.NaN, Number.POSITIVE_INFINITY, -1, 10_000_001])('拒绝无效测量值 %s', (value) => {
    expect(() => calculateTrends([measurement('x', '指标', value, '2026-08-01T00:00:00Z')])).toThrow('有效的非负数')
  })

  it('空列表返回空趋势', () => {
    expect(calculateTrends([])).toEqual([])
  })
})
