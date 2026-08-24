/** Package invariant for the account-private dsh-library provider. */
import type { Context } from '@deepseek-ai/cordis'
import type { InvariantFailure, InvariantInstaller } from '@deepseek-ai/dsh-invariants'

const PACKAGE_NAME = '@gerclaw/library-dsh'
export const name = 'gerclaw-library-dsh-invariant'
export const inject = ['invariants']
const install: InvariantInstaller = Object.assign(
  (scope: Context, fail: InvariantFailure) => {
    if (scope.get('gerclawLibrary') === undefined)
      fail('gerclawLibrary service is unavailable')
  },
  { inject: ['gerclawLibrary'] },
)
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
