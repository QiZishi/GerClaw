/** Package invariant for the isolated storage-domain provider. */
import type { Context } from '@deepseek-ai/cordis'
import type { InvariantFailure, InvariantInstaller } from '@deepseek-ai/dsh-invariants'

const PACKAGE_NAME = '@gerclaw/storage-domain-isolated'
export const name = 'gerclaw-storage-domain-isolated-invariant'
export const inject = ['invariants']
const install: InvariantInstaller = Object.assign(
  (scope: Context, fail: InvariantFailure) => {
    if (scope.get('storageDomain') === undefined)
      fail('storageDomain service is unavailable in the isolated realm')
  },
  { inject: ['storageDomain'] },
)
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
