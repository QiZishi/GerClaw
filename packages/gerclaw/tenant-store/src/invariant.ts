/** Package invariant for the GerClaw tenant store. */
import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'
const PACKAGE_NAME = '@gerclaw/tenant-store'
export const name = 'gerclaw-tenant-store-invariant'
export const inject = ['invariants']
// No runtime invariant: the tenant isolation Loader tests own storage checks.
const install: InvariantInstaller = () => {}
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
