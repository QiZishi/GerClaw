/** Package invariant for the GerClaw artifact service definition. */
import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'
const PACKAGE_NAME = '@gerclaw/artifact'
export const name = 'gerclaw-artifact-invariant'
export const inject = ['invariants']
// No runtime invariant: providers own artifact persistence checks.
const install: InvariantInstaller = () => {}
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
