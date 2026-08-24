/** Durable provider for dsh-multi-tenant's session-ownership seam. */
import { Service } from '@deepseek-ai/cordis'
import { defineDomain, domainTable, type Domain } from '@deepseek-ai/dsh-storage-domain'
import {
  TenantSessionStore,
} from 'dsh-multi-tenant/store'
import type { ClaimResult, SessionOwner } from 'dsh-multi-tenant'
import { z } from 'zod'

const ownerSchema = z.object({
  tenantId: z.string().min(1),
  userId: z.string().min(1),
})

const tenantOwnershipSpec = defineDomain({
  name: 'gerclaw_tenant_ownership',
  version: 1,
  tables: {
    owners: domainTable<string, SessionOwner>(ownerSchema),
  },
})

const settled = (): void => {}

/**
 * Serializes claim operations before writing through storage-domain. The
 * storage medium remains authoritative; the promise tail only preserves the
 * atomic claim contract when concurrent requests target the same session.
 */
export class DurableTenantSessionStore extends TenantSessionStore {
  static inject = ['storageDomain']

  private domain: Domain<typeof tenantOwnershipSpec> | undefined
  private claims: Promise<void> = Promise.resolve()

  protected async [Service.init](): Promise<void> {
    const domain = await this.ctx.storageDomain.open(tenantOwnershipSpec)
    this.domain = domain
    this.ctx.effect(() => async () => {
      this.domain = undefined
      await domain.close()
    }, 'gerclaw.tenant-store.close')
  }

  claim(sessionId: string, owner: SessionOwner): Promise<ClaimResult> {
    const result = this.claims.then(async () => {
      const owners = this.requireDomain().table('owners')
      const current = owners.get(sessionId)
      if (current !== undefined) {
        return current.tenantId === owner.tenantId && current.userId === owner.userId
          ? 'idempotent' as const
          : 'conflict' as const
      }
      await owners.put(sessionId, owner)
      return 'created' as const
    })
    this.claims = result.then(settled, settled)
    return result
  }

  async get(sessionId: string): Promise<SessionOwner | undefined> {
    await this.claims
    return this.requireDomain().table('owners').get(sessionId)
  }

  private requireDomain(): Domain<typeof tenantOwnershipSpec> {
    if (this.domain === undefined) throw new Error('tenant store is not active')
    return this.domain
  }
}

export default DurableTenantSessionStore
