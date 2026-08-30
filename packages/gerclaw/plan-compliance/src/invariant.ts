/** Package invariant for GerClaw plan compliance. */
import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'
const PACKAGE_NAME = '@gerclaw/plan-compliance'
export const name = 'gerclaw-plan-compliance-invariant'
export const inject = ['invariants']
// No runtime invariant: this event-only adapter has no service handle to inspect.
const install: InvariantInstaller = () => {}
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
