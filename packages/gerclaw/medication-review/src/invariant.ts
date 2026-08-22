import type { Context } from '@deepseek-ai/cordis'
import type {
  InvariantFailure,
  InvariantInstaller,
} from '@deepseek-ai/dsh-invariants'
const PACKAGE_NAME = '@gerclaw/medication-review'
export const name = 'gerclaw-medication-review-invariant'
export const inject = ['invariants']
const install: InvariantInstaller = Object.assign(
  (scope: Context, fail: InvariantFailure) => {
    if (scope.get('gerclawMedicationReview') === undefined)
      fail('gerclawMedicationReview service is unavailable')
  },
  { inject: ['gerclawMedicationReview'] },
)
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
