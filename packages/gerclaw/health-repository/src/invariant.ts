/** Package invariant for the GerClaw health repository service definition. */
import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'

const PACKAGE_NAME = '@gerclaw/health-repository'
export const name = 'gerclaw-health-repository-invariant'
export const inject = ['invariants']
// No runtime invariant: providers own repository persistence checks.
const install: InvariantInstaller = () => {}
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
