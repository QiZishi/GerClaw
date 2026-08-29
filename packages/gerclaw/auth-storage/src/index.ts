/**
 * Cordis persistence seam for GerClaw account credentials.
 *
 * The account table is deliberately separate from the authentication service:
 * auth owns password/session policy while this provider owns the durable
 * medium and the one-time migration boundary. The old credential reference
 * and accounts.json are read only during migration and are never overwritten.
 */
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { Service, type Context } from '@deepseek-ai/cordis'
import { credentialRef } from '@deepseek-ai/dsh-credentials'
import {
  defineDomain,
  domainTable,
  type Domain,
  type KvTable,
} from '@deepseek-ai/dsh-storage-domain'
import z from '@deepseek-ai/schemastery'
import { z as zod } from 'zod'

export interface GerclawAccount {
  id: string
  username: string
  audience: 'doctor' | 'patient'
  salt: string
  passwordHash: string
  recoverySalt: string
  recoveryHash: string
  createdAt: string
}

const accountSchema = zod.object({
  id: zod.string().min(1),
  username: zod.string().min(1),
  audience: zod.union([zod.literal('doctor'), zod.literal('patient')]),
  salt: zod.string().min(1),
  passwordHash: zod.string().min(1),
  recoverySalt: zod.string().min(1),
  recoveryHash: zod.string().min(1),
  createdAt: zod.string().min(1),
})

const migrationSchema = zod.object({
  version: zod.literal(1),
  source: zod.union([
    zod.literal('credentials'),
    zod.literal('accounts.json'),
    zod.literal('empty'),
  ]),
  migratedAt: zod.string().min(1),
})

const accountDomainSpec = defineDomain({
  name: 'gerclaw_auth_accounts',
  version: 1,
  global: {
    schema: migrationSchema,
    initial: { version: 1 as const, source: 'empty' as const, migratedAt: 'pending' },
  },
  tables: {
    accounts: domainTable<string, GerclawAccount>(accountSchema),
  },
})

const LEGACY_ACCOUNT_REF = credentialRef('GERCLAW_AUTH_ACCOUNTS')

interface LegacyRegistry {
  version?: unknown
  accounts?: unknown
}

export interface GerclawAccountStoreConfig {
  dataDir: string
}

export abstract class GerclawAccountStore extends Service {
  constructor(ctx: Context) { super(ctx, 'gerclawAccountStore') }
  abstract list(): GerclawAccount[]
  abstract findByUsername(username: string): GerclawAccount | undefined
  abstract findById(accountId: string): GerclawAccount | undefined
  abstract put(account: GerclawAccount): Promise<void>
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawAccountStore: GerclawAccountStore
  }
}

/** Durable account store over DSH storage-domain. */
export class StorageGerclawAccountStore extends GerclawAccountStore {
  static inject = ['storageDomain', 'credentials']
  static Config: z<GerclawAccountStoreConfig> = z.object({
    dataDir: z.string().required(),
  })

  private accounts: KvTable<string, GerclawAccount> | undefined
  private writes: Promise<void> = Promise.resolve()

  constructor(ctx: Context, private readonly config: GerclawAccountStoreConfig) {
    super(ctx)
  }

  protected async [Service.init](): Promise<void> {
    const domain = await this.ctx.storageDomain.open(accountDomainSpec)
    this.accounts = domain.table('accounts')
    await this.migrate(domain)
    this.ctx.effect(() => async () => {
      this.accounts = undefined
      await domain.close()
    }, 'gerclaw.auth-storage.close')
  }

  list(): GerclawAccount[] {
    return [...this.requireAccounts().entries()].map(([, account]) => account)
  }

  findByUsername(username: string): GerclawAccount | undefined {
    return this.requireAccounts().get(username)
  }

  findById(accountId: string): GerclawAccount | undefined {
    return this.list().find(account => account.id === accountId)
  }

  put(account: GerclawAccount): Promise<void> {
    const result = this.writes.then(() => this.requireAccounts().put(account.username, account))
    this.writes = result.then(() => undefined, () => undefined)
    return result
  }

  private requireAccounts(): KvTable<string, GerclawAccount> {
    if (this.accounts === undefined) throw new Error('账号存储尚未就绪')
    return this.accounts
  }

  private async migrate(domain: Domain<typeof accountDomainSpec>): Promise<void> {
    if (domain.global.get().migratedAt !== 'pending') return
    const existing = this.requireAccounts().size > 0
    if (existing) {
      await domain.global.set({ version: 1, source: 'empty', migratedAt: new Date().toISOString() })
      return
    }

    const fromCredentials = await this.readCredentialRegistry()
    if (fromCredentials !== undefined) {
      await this.writeRegistry(fromCredentials)
      await domain.global.set({ version: 1, source: 'credentials', migratedAt: new Date().toISOString() })
      return
    }

    const fromFile = await this.readLegacyFile()
    if (fromFile !== undefined) {
      await this.writeRegistry(fromFile)
      await domain.global.set({ version: 1, source: 'accounts.json', migratedAt: new Date().toISOString() })
      return
    }

    await domain.global.set({ version: 1, source: 'empty', migratedAt: new Date().toISOString() })
  }

  private async writeRegistry(registry: readonly GerclawAccount[]): Promise<void> {
    for (const account of registry) {
      await this.requireAccounts().put(account.username, account)
    }
  }

  private async readCredentialRegistry(): Promise<GerclawAccount[] | undefined> {
    const value = await this.ctx.credentials.resolve(LEGACY_ACCOUNT_REF)
    if (value === undefined) return undefined
    return parseRegistry(value.value)
  }

  private async readLegacyFile(): Promise<GerclawAccount[] | undefined> {
    try {
      const raw = await readFile(join(this.config.dataDir, 'accounts.json'), 'utf8')
      return parseRegistry(raw)
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return undefined
      throw error
    }
  }
}

function parseRegistry(raw: string): GerclawAccount[] {
  const parsed = JSON.parse(raw) as LegacyRegistry
  if (parsed.version !== 1 || !Array.isArray(parsed.accounts)) {
    throw new Error('旧账号数据版本不受支持')
  }
  return parsed.accounts.map(value => accountSchema.parse(value))
}

export default StorageGerclawAccountStore
