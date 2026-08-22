import type { Context } from '@deepseek-ai/cordis'
import type {
  InvariantFailure,
  InvariantInstaller,
} from '@deepseek-ai/dsh-invariants'
const PACKAGE_NAME = '@gerclaw/medical-evidence'
export const name = 'gerclaw-medical-evidence-invariant'
export const inject = ['invariants']
const install: InvariantInstaller = Object.assign(
  (scope: Context, fail: InvariantFailure) => {
    if (scope.get('gerclawMedicalEvidence') === undefined)
      fail('gerclawMedicalEvidence service is unavailable')
  },
  { inject: ['gerclawMedicalEvidence'] },
)
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
