/** Package invariant for the local GerClaw tenant host provider. */
import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'
const PACKAGE_NAME = '@gerclaw/tenant-host-local'
export const name = 'gerclaw-tenant-host-local-invariant'
export const inject = ['invariants']
// No runtime invariant: the tenant isolation Loader tests own host process checks.
const install: InvariantInstaller = () => {}
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
