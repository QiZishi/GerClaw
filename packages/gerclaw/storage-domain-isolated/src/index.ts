/**
 * Storage-domain adapter for a Loader-isolated storage realm.
 *
 * Derived from @deepseek-ai/dsh-storage-domain. The native provider's nested
 * backend lifecycle fiber inherits `storage` through its parent fiber. Cordis
 * service isolation deliberately terminates that inheritance boundary, so
 * this adapter declares `storage` on the nested fiber as well. Domain
 * semantics and cleanup remain owned by the native DomainFacility.
 */
import type { Context } from '@deepseek-ai/cordis'
import { storageBackendServiceKey } from '@deepseek-ai/dsh-storage'
import { DomainFacility } from '@deepseek-ai/dsh-storage-domain'
import z from '@deepseek-ai/schemastery'

export const name = 'gerclaw-storage-domain-isolated'
export const inject = ['storage']

export interface Config {
  backend: string
  routes?: Record<string, string>
}

export const Config: z<Config> = z.object({
  backend: z.string().required(),
  routes: z.dict(z.string()).default({}),
})

export function apply(ctx: Context, config: Config): Promise<void> {
  const backendServices = [...new Set([
    config.backend,
    ...Object.values(config.routes ?? {}),
  ])].map(storageBackendServiceKey)

  const fiber = ctx.inject(['storage', ...backendServices], (domainCtx) => {
    const facility = new DomainFacility(domainCtx, config)
    domainCtx.effect(() => {
      const unmount = domainCtx.storage.mount('domain', facility)
      return async () => {
        await facility.closeAll()
        unmount()
      }
    }, 'gerclaw.storage-domain-isolated.mount')
    domainCtx.provide('storageDomain', facility)
  })
  return Promise.resolve(fiber).then(() => {})
}
