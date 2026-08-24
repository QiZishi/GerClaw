/** Package invariant for the GerClaw library service definitions. */
import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'

const PACKAGE_NAME = '@gerclaw/library'
export const name = 'gerclaw-library-invariant'
export const inject = ['invariants']

/** No runtime invariant: providers own the mutable shared and private index relations. */
const install: InvariantInstaller = () => {}

export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
