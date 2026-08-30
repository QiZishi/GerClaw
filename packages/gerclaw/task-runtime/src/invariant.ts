/** Package invariant for the GerClaw task runtime service definition. */
import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'
const PACKAGE_NAME = '@gerclaw/task-runtime'
export const name = 'gerclaw-task-runtime-invariant'
export const inject = ['invariants']
// No runtime invariant: providers own task execution checks.
const install: InvariantInstaller = () => {}
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
