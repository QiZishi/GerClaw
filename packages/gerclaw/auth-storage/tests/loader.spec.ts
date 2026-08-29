import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { FiberState } from '@deepseek-ai/cordis'
import { boot } from '@deepseek-ai/dsh-app-boot'
import { afterEach, describe, expect, it } from 'vitest'
import type {} from '../src/index.ts'

const repoRoot = join(import.meta.dirname, '../../../..')
const pluginUrl = (relativePath: string): string => pathToFileURL(
  join(repoRoot, relativePath),
).href

const roots: string[] = []
const source = {
  timer: pluginUrl('vendor/timer/lib/index.js'),
  storage: pluginUrl('packages/storage/storage/lib/index.js'),
  storageJson: pluginUrl('packages/storage/storage-json/lib/index.js'),
  storageDomain: pluginUrl('packages/storage/storage-domain/lib/index.js'),
  credentials: pluginUrl('packages/credentials/credentials-local/lib/index.js'),
  authStorage: pluginUrl('packages/gerclaw/auth-storage/lib/types/index.js'),
  auth: pluginUrl('packages/gerclaw/auth/lib/types/index.js'),
}

afterEach(async () => {
  await Promise.all(roots.splice(0).map(root => rm(root, { recursive: true, force: true })))
})

const quote = (value: string): string => JSON.stringify(value)

const configFor = (root: string, includeAuth = true): string => [
  '- id: timer',
  `  name: ${quote(source.timer)}`,
  '- id: storage',
  `  name: ${quote(source.storage)}`,
  '- id: storage-json',
  `  name: ${quote(source.storageJson)}`,
  `  config: { root: ${quote(join(root, 'storage'))} }`,
  '- id: storage-domain',
  `  name: ${quote(source.storageDomain)}`,
  '  config: { backend: json }',
  '- id: credentials',
  `  name: ${quote(source.credentials)}`,
  `  config: { path: ${quote(join(root, 'credentials.yaml'))}, watch: false }`,
  ...(includeAuth ? [
    '- id: account-store',
    `  name: ${quote(source.authStorage)}`,
    `  config: { dataDir: ${quote(root)} }`,
    '- id: auth',
    `  name: ${quote(source.auth)}`,
    '  config: { sessionTtlSeconds: 3600 }',
  ] : []),
].join('\n')

const account = {
  id: 'account-from-legacy',
  username: 'legacy-user',
  audience: 'patient',
  salt: '00112233445566778899aabbccddeeff',
  passwordHash: '00112233445566778899aabbccddeeff',
  recoverySalt: 'ffeeddccbbaa99887766554433221100',
  recoveryHash: 'ffeeddccbbaa99887766554433221100',
  createdAt: '2026-08-25T00:00:00.000Z',
} as const

describe('GerClaw account persistence through the real DSH Loader', () => {
  it('registers and recovers an isolated account without touching persistent test accounts', async () => {
    const root = await mkdtemp(join(tmpdir(), 'gerclaw-auth-recovery-'))
    roots.push(root)
    const config = join(root, 'cordis.yml')
    await writeFile(config, configFor(root))
    const first = await boot('gerclaw-auth-recovery-test', config)
    const initialPassword = 'Initial-test-password-2026'
    const recoveredPassword = 'Recovered-test-password-2026'
    try {
      const auth = first.get('gerclawAuth')!
      const registered = await auth.register('isolated-recovery-user', initialPassword, 'doctor')
      await expect(auth.login('isolated-recovery-user', initialPassword)).resolves.toMatchObject({
        account: { id: registered.account.id, audience: 'doctor' },
      })
      const nextCode = await auth.recover(
        'isolated-recovery-user',
        registered.recoveryCode,
        recoveredPassword,
      )
      expect(nextCode).not.toBe(registered.recoveryCode)
      await expect(auth.login('isolated-recovery-user', initialPassword)).rejects.toThrow('用户名或密码不正确')
      await expect(auth.recover(
        'isolated-recovery-user',
        registered.recoveryCode,
        'Another-test-password-2026',
      )).rejects.toThrow('恢复信息不正确')
    } finally {
      await first.fiber.dispose()
    }
    const restored = await boot('gerclaw-auth-recovery-reload-test', config)
    try {
      await expect(restored.get('gerclawAuth')!.login(
        'isolated-recovery-user',
        recoveredPassword,
      )).resolves.toMatchObject({ account: { audience: 'doctor' } })
    } finally {
      await restored.fiber.dispose()
    }
  })

  it('migrates accounts.json once and keeps the legacy source read-only', async () => {
    const root = await mkdtemp(join(tmpdir(), 'gerclaw-auth-storage-'))
    roots.push(root)
    await mkdir(root, { recursive: true })
    const legacyPath = join(root, 'accounts.json')
    await writeFile(legacyPath, JSON.stringify({ version: 1, accounts: [account] }))
    const config = join(root, 'cordis.yml')
    await writeFile(config, configFor(root))
    const ctx = await boot('gerclaw-auth-storage-migration-test', config)
    try {
      const store = ctx.get('gerclawAccountStore')
      expect(store?.findByUsername('legacy-user')).toMatchObject(account)
      expect(ctx.storageDomain.get('gerclaw_auth_accounts')?.global.get()).toMatchObject({
        version: 1,
        source: 'accounts.json',
      })
      await expect(readFile(legacyPath, 'utf8')).resolves.toContain('legacy-user')
    } finally {
      await ctx.fiber.dispose()
    }
  })

  it('migrates the legacy GERCLAW_AUTH_ACCOUNTS reference before the file source', async () => {
    const root = await mkdtemp(join(tmpdir(), 'gerclaw-auth-credential-migration-'))
    roots.push(root)
    const legacy = { ...account, id: 'account-from-credential', username: 'credential-user' }
    const previous = process.env.GERCLAW_AUTH_ACCOUNTS
    process.env.GERCLAW_AUTH_ACCOUNTS = JSON.stringify({ version: 1, accounts: [legacy] })
    try {
      const config = join(root, 'cordis.yml')
      await writeFile(config, configFor(root))
      const ctx = await boot('gerclaw-auth-credential-migration-test', config)
      try {
        const store = ctx.get('gerclawAccountStore')
        expect(store?.findByUsername('credential-user')).toMatchObject(legacy)
        expect(ctx.storageDomain.get('gerclaw_auth_accounts')?.global.get()).toMatchObject({
          version: 1,
          source: 'credentials',
        })
      } finally {
        await ctx.fiber.dispose()
      }
    } finally {
      if (previous === undefined) delete process.env.GERCLAW_AUTH_ACCOUNTS
      else process.env.GERCLAW_AUTH_ACCOUNTS = previous
    }
  })

  it('keeps auth pending while the account provider is disabled, then restores it', async () => {
    const root = await mkdtemp(join(tmpdir(), 'gerclaw-auth-storage-hotplug-'))
    roots.push(root)
    const config = join(root, 'cordis.yml')
    await writeFile(config, configFor(root))
    const ctx = await boot('gerclaw-auth-storage-hotplug-test', config)
    try {
      const provider = [...ctx.loader.entries()].find(entry => entry.options.id === 'account-store')
      const auth = [...ctx.loader.entries()].find(entry => entry.options.id === 'auth')
      expect(provider?.fiber?.state).toBe(FiberState.ACTIVE)
      expect(auth?.fiber?.state).toBe(FiberState.ACTIVE)
      expect(ctx.get('gerclawAccountStore')).toBeDefined()
      expect(ctx.get('gerclawAuth')).toBeDefined()

      await ctx.loader.update(provider!.id, { disabled: true })
      await ctx.loader.await()
      expect(provider?.fiber).toBeUndefined()
      expect(auth?.fiber?.state).toBe(FiberState.PENDING)
      expect(ctx.get('gerclawAccountStore')).toBeUndefined()
      expect(ctx.get('gerclawAuth')).toBeUndefined()

      await ctx.loader.update(provider!.id, { disabled: false })
      await ctx.loader.await()
      expect(provider?.fiber?.state).toBe(FiberState.ACTIVE)
      expect(auth?.fiber?.state).toBe(FiberState.ACTIVE)
      expect(ctx.get('gerclawAccountStore')).toBeDefined()
      expect(ctx.get('gerclawAuth')).toBeDefined()
    } finally {
      await ctx.fiber.dispose()
    }
  })
})
