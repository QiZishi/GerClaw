/** Package invariant for the GerClaw speech service. */
import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'
const PACKAGE_NAME = '@gerclaw/speech'
export const name = 'gerclaw-speech-invariant'
export const inject = ['invariants']
// No runtime invariant: provider activation is validated by the real Loader lifecycle matrix.
const install: InvariantInstaller = () => {}
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
