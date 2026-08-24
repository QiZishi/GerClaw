/** Replaceable Service Definition for one authenticated principal's DSH Host. */
import { Context, Service } from '@deepseek-ai/cordis'
import type { TenantPrincipal } from 'dsh-multi-tenant'

export interface TenantHostRequest {
  principal: TenantPrincipal
  guest: boolean
  audience: 'doctor' | 'patient'
}

export interface TenantHostEndpoint {
  principal: TenantPrincipal
  host: '127.0.0.1'
  port: number
  guest: boolean
  lastSeen: number
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawTenantHost: TenantHostRuntime
  }
}

export abstract class TenantHostRuntime extends Service {
  constructor(ctx: Context) {
    super(ctx, 'gerclawTenantHost')
  }

  abstract ensure(request: TenantHostRequest): Promise<TenantHostEndpoint>
  abstract disposePrincipal(principal: TenantPrincipal): Promise<void>
}

export default TenantHostRuntime
