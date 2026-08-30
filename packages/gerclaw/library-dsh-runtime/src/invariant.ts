import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'

const PACKAGE_NAME = '@gerclaw/library-dsh-runtime'
export const name = 'gerclaw-library-dsh-runtime-invariant'
export const inject = ['invariants']

// No runtime invariant: retrieval Loader tests own provider checks.
const install: InvariantInstaller = () => {}

export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
