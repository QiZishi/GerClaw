/** Owner-authoritative structured health profile, separate from assistant memory. */
import { Context, Service } from '@deepseek-ai/cordis'

export interface HealthProfile {
  profileId: string
  displayName?: string
  age?: number
  sex?: 'female' | 'male' | 'other' | 'unknown'
  heightCm?: number
  weightKg?: number
  allergies: string[]
  conditions: string[]
  medications: string[]
  goals: string[]
  preferences: string[]
  revision: number
  updatedAt: string
}

const textList = (values: unknown, max: number): string[] => {
  if (!Array.isArray(values)) return []
  return [...new Set(values.map(String).map(value => value.trim()).filter(Boolean))].slice(0, max)
}

export function normalizeHealthProfile(
  input: Partial<HealthProfile>,
  previous?: HealthProfile,
): HealthProfile {
  const age = input.age ?? previous?.age
  if (age !== undefined && (!Number.isInteger(age) || age < 0 || age > 130))
    throw new Error('年龄必须为 0 到 130 的整数')
  return {
    profileId: previous?.profileId ?? input.profileId ?? crypto.randomUUID(),
    ...(input.displayName?.trim() ? { displayName: input.displayName.trim() } : {}),
    ...(age === undefined ? {} : { age }),
    ...(input.sex === undefined ? {} : { sex: input.sex }),
    ...(input.heightCm === undefined ? {} : { heightCm: input.heightCm }),
    ...(input.weightKg === undefined ? {} : { weightKg: input.weightKg }),
    allergies: textList(input.allergies ?? previous?.allergies, 50),
    conditions: textList(input.conditions ?? previous?.conditions, 50),
    medications: textList(input.medications ?? previous?.medications, 50),
    goals: textList(input.goals ?? previous?.goals, 20),
    preferences: textList(input.preferences ?? previous?.preferences, 30),
    revision: (previous?.revision ?? 0) + 1,
    updatedAt: new Date().toISOString(),
  }
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawHealthProfile: HealthProfileService
  }
}

export class HealthProfileService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'gerclawHealthProfile')
  }

  normalize(input: Partial<HealthProfile>, previous?: HealthProfile): HealthProfile {
    return normalizeHealthProfile(input, previous)
  }
}

export default HealthProfileService
