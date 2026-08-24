/** DSH storage-domain provider for account-local GerClaw health records. */
import { Service } from '@deepseek-ai/cordis'
import { defineDomain, domainTable, type KvTable } from '@deepseek-ai/dsh-storage-domain'
import { z } from 'zod'
import { HealthRepository, type HealthRecord } from '@gerclaw/health-repository'

const recordSchema = z.object({
  kind: z.string(),
  value: z.unknown(),
  updatedAt: z.string(),
})

export const healthRepositoryDomainSpec = defineDomain({
  name: 'gerclaw_data',
  version: 1,
  tables: { records: domainTable<string, HealthRecord>(recordSchema) },
})

/** Preserves the existing gerclaw_data domain while moving ownership out of the app plugin. */
export class StorageHealthRepository extends HealthRepository {
  static inject = ['storageDomain']
  private records: KvTable<string, HealthRecord> | undefined

  protected async [Service.init](): Promise<void> {
    const domain = await this.ctx.storageDomain.open(healthRepositoryDomainSpec)
    this.records = domain.table('records')
    this.ctx.effect(() => async () => {
      this.records = undefined
      await domain.close()
    }, 'gerclaw.health-repository.domain')
  }

  private table(): KvTable<string, HealthRecord> {
    if (this.records === undefined) throw new Error('健康数据存储尚未就绪')
    return this.records
  }

  get(key: string): unknown {
    return this.table().get(key)?.value
  }

  async put(key: string, kind: string, value: unknown): Promise<void> {
    await this.table().put(key, { kind, value, updatedAt: new Date().toISOString() })
  }

  list<T>(kind: string): T[] {
    return [...this.table().entries()]
      .filter(([, entry]) => entry.kind === kind)
      .sort((a, b) => b[1].updatedAt.localeCompare(a[1].updatedAt))
      .map(([, entry]) => entry.value as T)
  }

  async delete(key: string): Promise<boolean> {
    if (this.table().get(key) === undefined) return false
    await this.table().delete(key)
    return true
  }
}

export default StorageHealthRepository
