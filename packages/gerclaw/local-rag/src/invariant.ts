import type { Context } from '@deepseek-ai/cordis'
import type {
  InvariantFailure,
  InvariantInstaller,
} from '@deepseek-ai/dsh-invariants'
const PACKAGE_NAME = '@gerclaw/shared-knowledge'
export const name = 'gerclaw-shared-knowledge-invariant'
export const inject = ['invariants']
const install: InvariantInstaller = Object.assign(
  (scope: Context, fail: InvariantFailure) => {
    if (scope.get('gerclawSharedKnowledge') === undefined)
      fail('gerclawSharedKnowledge service is unavailable')
  },
  { inject: ['gerclawSharedKnowledge'] },
)
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
