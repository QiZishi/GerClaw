/** Package invariant for the storage-backed GerClaw account provider. */
import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'

const PACKAGE_NAME = '@gerclaw/auth-storage'
export const name = 'gerclaw-auth-storage-invariant'
export const inject = ['invariants']
// No runtime invariant: authentication Loader tests own storage checks.
const install: InvariantInstaller = () => {}
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
