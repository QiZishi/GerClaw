/** Replaceable account-local repository for GerClaw health records. */
import { Context, Service } from '@deepseek-ai/cordis'

export interface HealthRecord<T = unknown> {
  kind: string
  value: T
  updatedAt: string
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    healthRepository: HealthRepository
  }
}

/** Storage seam; providers own persistence handles and account isolation. */
export abstract class HealthRepository extends Service {
  constructor(ctx: Context) { super(ctx, 'healthRepository') }

  abstract get(key: string): unknown
  abstract put(key: string, kind: string, value: unknown): Promise<void>
  abstract list<T>(kind: string): T[]
  abstract delete(key: string): Promise<boolean>
}

export default HealthRepository
