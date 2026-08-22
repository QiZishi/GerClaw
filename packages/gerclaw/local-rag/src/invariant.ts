import type { Context } from '@deepseek-ai/cordis'
import type {
  InvariantFailure,
  InvariantInstaller,
} from '@deepseek-ai/dsh-invariants'
const PACKAGE_NAME = '@gerclaw/local-rag'
export const name = 'gerclaw-local-rag-invariant'
export const inject = ['invariants']
const install: InvariantInstaller = Object.assign(
  (scope: Context, fail: InvariantFailure) => {
    if (scope.get('gerclawRag') === undefined)
      fail('gerclawRag service is unavailable')
  },
  { inject: ['gerclawRag'] },
)
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
