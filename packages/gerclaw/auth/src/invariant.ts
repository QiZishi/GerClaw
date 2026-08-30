/** Package invariant for GerClaw authentication. */
import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'
const PACKAGE_NAME = '@gerclaw/auth'
export const name = 'gerclaw-auth-invariant'
export const inject = ['invariants']
// No runtime invariant: the real Loader authentication lifecycle tests own the stateful checks.
const install: InvariantInstaller = () => {}
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
