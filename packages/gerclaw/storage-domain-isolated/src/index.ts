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
import {
  Config as StorageDomainConfig,
  DomainFacility,
  type Config as StorageDomainConfigType,
} from '@deepseek-ai/dsh-storage-domain'

export const name = 'gerclaw-storage-domain-isolated'
export const inject = ['storage']

export type Config = StorageDomainConfigType
export const Config = StorageDomainConfig

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
