import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'
const PACKAGE_NAME = '@gerclaw/launcher'
export const name = 'gerclaw-launcher-invariant'
export const inject = ['invariants']
// No runtime invariant: the launcher is a process entry and mounts no service.
const install: InvariantInstaller = () => {}
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
