import type { Context } from '@deepseek-ai/cordis'
import type {
  InvariantFailure,
  InvariantInstaller,
} from '@deepseek-ai/dsh-invariants'
const PACKAGE_NAME = '@gerclaw/tenant-gateway'
export const name = 'gerclaw-tenant-gateway-invariant'
export const inject = ['invariants']
const install: InvariantInstaller = Object.assign(
  (scope: Context, fail: InvariantFailure) => {
    if (scope.get('gerclawTenantGateway') === undefined)
      fail('gerclawTenantGateway service is unavailable')
  },
  { inject: ['gerclawTenantGateway'] },
)
export const apply = (ctx: Context): Promise<() => void> =>
  Promise.resolve(ctx.invariants.register(PACKAGE_NAME, install))
