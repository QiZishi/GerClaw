/** GerClaw account authentication provider derived from dsh-login's auth core. */
import {
  randomBytes,
  randomUUID,
  scrypt as scryptCallback,
  timingSafeEqual,
} from 'node:crypto'
import { promisify } from 'node:util'
import { Context, Service } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/cordis-plugin-timer'
import z from '@deepseek-ai/schemastery'
import type { GerclawAccount, GerclawAccountStore } from '@gerclaw/auth-storage'

const scrypt = promisify(scryptCallback)
export type { GerclawAccount } from '@gerclaw/auth-storage'

export interface GerclawLoginSession {
  accountId: string
  username: string
  audience: 'doctor' | 'patient'
  guest: boolean
  lastSeen: number
  expiresAt: number
}

export interface GerclawAuthConfig {
  sessionTtlSeconds: number
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawAuth: GerclawAuthService
  }
}

const hashSecret = async (secret: string, salt: string): Promise<string> => {
  const derived = await scrypt(secret, Buffer.from(salt, 'hex'), 32)
  return Buffer.from(derived as ArrayBuffer).toString('hex')
}

const equalHash = (left: string, right: string): boolean => {
  const a = Buffer.from(left, 'hex')
  const b = Buffer.from(right, 'hex')
  return a.length === b.length && timingSafeEqual(a, b)
}

const recoveryCode = (): string => randomBytes(9).toString('base64url')
const settled = (): void => {}

export class GerclawAuthService extends Service {
  static inject = ['gerclawAccountStore', 'timer']
  static Config: z<GerclawAuthConfig> = z.object({
    sessionTtlSeconds: z.number().min(60).default(2_592_000),
  })

  private readonly sessions = new Map<string, GerclawLoginSession>()
  private writes: Promise<void> = Promise.resolve()

  constructor(
    ctx: Context,
    private readonly config: GerclawAuthConfig,
  ) {
    super(ctx, 'gerclawAuth')
  }

  private get accountStore(): GerclawAccountStore {
    return this.ctx.gerclawAccountStore
  }

  protected [Service.init](): void {
    this.ctx.interval(() => { this.sweepExpired() }, 60_000)
    this.ctx.effect(() => () => { this.sessions.clear() }, 'gerclaw.auth.sessions.clear')
  }

  async register(
    usernameInput: string,
    password: string,
    audience: 'doctor' | 'patient',
  ): Promise<{ account: GerclawAccount; token: string; recoveryCode: string }> {
    const username = this.normalizeUsername(usernameInput)
    this.validatePassword(password)
    return this.serialize(async () => {
      if (this.accountStore.findByUsername(username) !== undefined) {
        throw new Error('用户名已存在')
      }
      const salt = randomBytes(16).toString('hex')
      const recoverySalt = randomBytes(16).toString('hex')
      const code = recoveryCode()
      const account: GerclawAccount = {
        id: randomUUID(),
        username,
        audience,
        salt,
        passwordHash: await hashSecret(password, salt),
        recoverySalt,
        recoveryHash: await hashSecret(code, recoverySalt),
        createdAt: new Date().toISOString(),
      }
      await this.accountStore.put(account)
      return { account, token: this.createSession(account), recoveryCode: code }
    })
  }

  async login(usernameInput: string, password: string): Promise<{ account: GerclawAccount; token: string }> {
    const username = this.normalizeUsername(usernameInput)
    const account = this.accountStore.findByUsername(username)
    if (
      account === undefined
      || !equalHash(await hashSecret(password, account.salt), account.passwordHash)
    ) {
      throw new Error('用户名或密码不正确')
    }
    return { account, token: this.createSession(account) }
  }

  guest(): { token: string; session: GerclawLoginSession } {
    const token = randomBytes(32).toString('base64url')
    const now = Date.now()
    const session: GerclawLoginSession = {
      accountId: `guest-${randomUUID()}`,
      username: '游客',
      audience: 'patient',
      guest: true,
      lastSeen: now,
      expiresAt: now + this.config.sessionTtlSeconds * 1_000,
    }
    this.sessions.set(token, session)
    return { token, session }
  }

  verify(token: string | undefined): GerclawLoginSession | undefined {
    if (token === undefined || token.length === 0) return undefined
    const session = this.sessions.get(token)
    if (session === undefined) return undefined
    if (Date.now() >= session.expiresAt) {
      this.sessions.delete(token)
      return undefined
    }
    session.lastSeen = Date.now()
    return session
  }

  revoke(token: string): GerclawLoginSession | undefined {
    const session = this.sessions.get(token)
    this.sessions.delete(token)
    return session
  }

  async recover(usernameInput: string, code: string, password: string): Promise<string> {
    const username = this.normalizeUsername(usernameInput)
    this.validatePassword(password)
    return this.serialize(async () => {
      const account = this.accountStore.findByUsername(username)
      if (
        account === undefined
        || !equalHash(await hashSecret(code, account.recoverySalt), account.recoveryHash)
      ) {
        throw new Error('恢复信息不正确')
      }
      const { account: updated, code: nextCode } = await this.rotateCredentials(account, password)
      await this.accountStore.put(updated)
      this.revokeAccountSessions(account.id)
      return nextCode
    })
  }

  async changePassword(
    accountId: string,
    currentPassword: string,
    password: string,
    keepToken: string,
  ): Promise<string> {
    this.validatePassword(password)
    return this.serialize(async () => {
      const account = this.accountStore.findById(accountId)
      if (
        account === undefined
        || !equalHash(await hashSecret(currentPassword, account.salt), account.passwordHash)
      ) {
        throw new Error('当前密码不正确')
      }
      const { account: updated, code } = await this.rotateCredentials(account, password)
      await this.accountStore.put(updated)
      this.revokeAccountSessions(account.id, keepToken)
      return code
    })
  }

  private async rotateCredentials(
    account: GerclawAccount,
    password: string,
  ): Promise<{ account: GerclawAccount; code: string }> {
    const code = recoveryCode()
    const salt = randomBytes(16).toString('hex')
    const recoverySalt = randomBytes(16).toString('hex')
    return {
      account: {
        ...account,
        salt,
        passwordHash: await hashSecret(password, salt),
        recoverySalt,
        recoveryHash: await hashSecret(code, recoverySalt),
      },
      code,
    }
  }

  private createSession(account: GerclawAccount): string {
    const token = randomBytes(32).toString('base64url')
    const now = Date.now()
    this.sessions.set(token, {
      accountId: account.id,
      username: account.username,
      audience: account.audience,
      guest: false,
      lastSeen: now,
      expiresAt: now + this.config.sessionTtlSeconds * 1_000,
    })
    return token
  }

  private revokeAccountSessions(accountId: string, keepToken?: string): void {
    for (const [token, session] of this.sessions) {
      if (session.accountId === accountId && token !== keepToken) this.sessions.delete(token)
    }
  }

  private sweepExpired(): void {
    const now = Date.now()
    for (const [token, session] of this.sessions) {
      if (now >= session.expiresAt) this.sessions.delete(token)
    }
  }

  private normalizeUsername(value: string): string {
    const username = value.trim().toLowerCase()
    if (!/^[\p{L}\p{N}_.-]{3,32}$/u.test(username)) {
      throw new Error('用户名需为 3 至 32 个字符')
    }
    return username
  }

  private validatePassword(password: string): void {
    if (password.length < 8 || password.length > 128) {
      throw new Error('密码需为 8 至 128 个字符')
    }
  }

  private serialize<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.writes.then(operation)
    this.writes = result.then(settled, settled)
    return result
  }
}

export default GerclawAuthService
