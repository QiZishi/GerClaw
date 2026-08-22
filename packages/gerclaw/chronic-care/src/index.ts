/** Self-reported chronic condition measurements with arithmetic-only trends. */
import { Context, Service } from '@deepseek-ai/cordis'

export interface ChronicMeasurement {
  measurementId: string
  conditionId: string
  metricLabel: string
  value: number
  unit: string
  measuredAt: string
  createdAt: string
}

export interface ChronicTrend {
  metricLabel: string
  unit: string
  direction: 'up' | 'down' | 'unchanged' | 'first'
  latestValue: number
  previousValue?: number
  latestMeasuredAt: string
  previousMeasuredAt?: string
}

export function calculateTrends(items: ChronicMeasurement[]): ChronicTrend[] {
  const groups = new Map<string, ChronicMeasurement[]>()
  for (const item of items) {
    if (!Number.isFinite(item.value) || item.value < 0 || item.value > 10_000_000)
      throw new Error('测量值必须是有效的非负数')
    const key = `${item.metricLabel}\0${item.unit}`
    groups.set(key, [...(groups.get(key) ?? []), item])
  }
  return [...groups.values()].map((group) => {
    group.sort((a, b) => a.measuredAt.localeCompare(b.measuredAt))
    const latest = group.at(-1)
    if (!latest) throw new Error('缺少测量记录')
    const previous = group.at(-2)
    return {
      metricLabel: latest.metricLabel,
      unit: latest.unit,
      direction:
        previous === undefined
          ? 'first'
          : latest.value > previous.value
            ? 'up'
            : latest.value < previous.value
              ? 'down'
              : 'unchanged',
      latestValue: latest.value,
      ...(previous === undefined
        ? {}
        : {
          previousValue: previous.value,
          previousMeasuredAt: previous.measuredAt,
        }),
      latestMeasuredAt: latest.measuredAt,
    }
  })
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawChronicCare: ChronicCareService
  }
}

export class ChronicCareService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'gerclawChronicCare')
  }

  trends(items: ChronicMeasurement[]): ChronicTrend[] {
    return calculateTrends(items)
  }
}

export default ChronicCareService
