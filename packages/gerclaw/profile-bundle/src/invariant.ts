import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'
const PACKAGE_NAME = '@gerclaw/profile-bundle'
export const name = 'gerclaw-profile-bundle-invariant'
export const inject = ['invariants']
// No runtime invariant: this package is a static profile patch carrier.
const install: InvariantInstaller = () => {}
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
