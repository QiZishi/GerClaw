import type { Context } from '@deepseek-ai/cordis'
import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'

const PACKAGE_NAME = '@gerclaw/client-ui'

export const name = 'gerclaw-client-ui-invariant'
export const inject = ['invariants']

const install: InvariantInstaller = () => {
  // No runtime invariant: this client-only package owns presentation extensions.
}

export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
