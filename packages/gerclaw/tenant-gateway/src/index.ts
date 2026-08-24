/** Account authentication and per-account real-DSH Host lifecycle gateway. */
import {
  randomBytes,
  randomUUID,
  scrypt as scryptCallback,
  timingSafeEqual,
} from 'node:crypto'
import { spawn, type ChildProcess } from 'node:child_process'
import {
  createServer,
  request as httpRequest,
  type IncomingMessage,
  type ServerResponse,
} from 'node:http'
import {
  cp,
  lstat,
  mkdir,
  readFile,
  readdir,
  rename,
  rm,
  symlink,
  unlink,
  writeFile,
} from 'node:fs/promises'
import { join } from 'node:path'
import { promisify } from 'node:util'
import type { Duplex } from 'node:stream'
import { Context, Service } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-host-webserver'

const scrypt = promisify(scryptCallback)
const COOKIE = 'gerclaw_session'
const THIRTY_MINUTES = 30 * 60 * 1000
const CHILD_PLUGIN_PACKAGES = [
  '@anysearch/anysearch-dsh',
  '@gerclaw/app',
  '@gerclaw/client-ui',
  '@gerclaw/cga',
  '@gerclaw/chronic-care',
  '@gerclaw/companion',
  '@gerclaw/health-profile',
  '@gerclaw/local-rag',
  '@gerclaw/medical-evidence',
  '@gerclaw/medication-review',
  '@gerclaw/prescription',
  '@gerclaw/risk-alert',
  '@gerclaw/skills',
  '@gerclaw/system-prompt',
  '@gerclaw/voice',
  '@deepseek-ai/dsh-storage-sqlite',
  'dsh-better-sidebar',
  'dsh-library',
  'dsh-mineru',
] as const
interface Account {
  id: string
  username: string
  audience: 'doctor' | 'patient'
  salt: string
  passwordHash: string
  recoverySalt: string
  recoveryHash: string
  createdAt: string
}
interface LoginSession {
  accountId: string
  guest: boolean
  lastSeen: number
}
interface Host {
  process: ChildProcess
  port: number
  lastSeen: number
  guest: boolean
}
interface Registry {
  version: 1
  accounts: Account[]
}
export interface TenantGatewayConfig {
  rootDir: string
  dataDir: string
  childPatch: string
  idleMs?: number
}

const hashSecret = async (secret: string, salt: string) => {
  const derived = await scrypt(secret, Buffer.from(salt, 'hex'), 32)
  return Buffer.from(derived as ArrayBuffer).toString('hex')
}
const equalHash = (left: string, right: string) => {
  const a = Buffer.from(left, 'hex')
  const b = Buffer.from(right, 'hex')
  return a.length === b.length && timingSafeEqual(a, b)
}
const recoveryCode = () => randomBytes(9).toString('base64url')
const rotateCredentials = async (account: Account, password: string) => {
  const code = recoveryCode()
  account.salt = randomBytes(16).toString('hex')
  account.passwordHash = await hashSecret(password, account.salt)
  account.recoverySalt = randomBytes(16).toString('hex')
  account.recoveryHash = await hashSecret(code, account.recoverySalt)
  return code
}
const json = (res: ServerResponse, status: number, value: unknown) => {
  const body = JSON.stringify(value)
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  })
  res.end(body)
}
const body = async (req: IncomingMessage) => {
  const chunks: Buffer[] = []
  let total = 0
  for await (const chunk of req as AsyncIterable<Uint8Array>) {
    const part = Buffer.from(chunk)
    total += part.length
    if (total > 64 * 1024) throw new Error('请求内容过大')
    chunks.push(part)
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}') as Record<
    string,
    unknown
  >
}
const cookies = (req: IncomingMessage): Record<string, string> => {
  const result: Record<string, string> = {}
  for (const part of (req.headers.cookie ?? '').split(';')) {
    const separator = part.indexOf('=')
    if (separator < 1) continue
    result[part.slice(0, separator).trim()] = part.slice(separator + 1).trim()
  }
  return result
}
const asText = (value: unknown): string =>
  typeof value === 'string' || typeof value === 'number'
    ? String(value)
    : ''
const safeMessage = (error: unknown) =>
  error instanceof Error ? error.message : '操作失败'

const syncControlledDirectory = async (
  source: string,
  target: string,
  label: string,
  replaceManagedFiles = false,
): Promise<void> => {
  await mkdir(target, { recursive: true })
  for (const entry of await readdir(source, { withFileTypes: true })) {
    const from = join(source, entry.name)
    const to = join(target, entry.name)
    if (entry.isDirectory()) {
      await syncControlledDirectory(from, to, label, replaceManagedFiles)
      continue
    }
    if (!entry.isFile()) continue
    try {
      const [expected, existing] = await Promise.all([
        readFile(from),
        readFile(to),
      ])
      if (!expected.equals(existing)) {
        if (!replaceManagedFiles)
          throw new Error(`${label}文件冲突：${entry.name}`)
        await cp(from, to, { force: true })
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
      await cp(from, to, { force: false, errorOnExist: true })
    }
  }
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawTenantGateway: GerclawTenantGateway
  }
}
export class GerclawTenantGateway extends Service {
  static inject = ['webServer']
  private registry: Registry = { version: 1, accounts: [] }
  private readonly sessions = new Map<string, LoginSession>()
  private readonly hosts = new Map<string, Host>()
  private readonly hostStarts = new Map<string, Promise<Host>>()
  private timer?: NodeJS.Timeout
  constructor(
    ctx: Context,
    private readonly config: TenantGatewayConfig,
  ) {
    super(ctx, 'gerclawTenantGateway')
  }
  protected async [Service.init](): Promise<void> {
    await mkdir(join(this.config.dataDir, 'accounts'), { recursive: true })
    await mkdir(join(this.config.dataDir, 'guests'), { recursive: true })
    try {
      this.registry = JSON.parse(
        await readFile(join(this.config.dataDir, 'accounts.json'), 'utf8'),
      ) as Registry
    } catch {}
    await this.sweepGuests()
    const auth = this.ctx.webServer.register({
      kind: 'prefix',
      path: '/auth',
      handler: (req, res) => this.auth(req, res),
    })
    const serveIcon = async (_req: IncomingMessage, res: ServerResponse) => {
      const data = await readFile(join(this.config.rootDir, 'icon.png'))
      res.writeHead(200, {
        'Content-Type': 'image/png',
        'Cache-Control': 'public,max-age=3600',
      })
      res.end(data)
    }
    const icon = this.ctx.webServer.register({
      kind: 'exact',
      path: '/brand-icon.png',
      handler: serveIcon,
    })
    const favicon = this.ctx.webServer.register({
      kind: 'exact',
      path: '/favicon.ico',
      handler: serveIcon,
    })
    const fallback = this.ctx.webServer.registerFallback((req, res) =>
      this.route(req, res),
    )
    const upgrades = [
      '/api/events.mux',
      '/api/events.host',
      '/gerclaw/api/voice/asr-stream',
      '/sidebar/ws/terminal',
      '/sidebar/ws/agent-terminals',
    ].map(path => this.ctx.webServer.registerUpgrade({
      path,
      handler: (req, socket, head) => this.upgrade(req, socket, head),
    }))
    this.timer = setInterval(() => {
      void this.reap()
    }, 60_000)
    this.timer.unref()
    this.ctx.effect(
      () => async () => {
        auth()
        icon()
        favicon()
        fallback()
        for (const dispose of upgrades) dispose()
        if (this.timer) clearInterval(this.timer)
        await Promise.all(
          [...this.hosts.keys()].map(id => this.stopHost(id, false)),
        )
      },
      'gerclaw.tenant-gateway',
    )
  }
  private async save() {
    const path = join(this.config.dataDir, 'accounts.json')
    const temp = `${path}.${process.pid}.tmp`
    await writeFile(temp, JSON.stringify(this.registry), { mode: 0o600 })
    await rename(temp, path)
  }
  private setCookie(res: ServerResponse, token: string) {
    res.setHeader(
      'Set-Cookie',
      `${COOKIE}=${token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000`,
    )
  }
  private current(req: IncomingMessage): [string, LoginSession] | undefined {
    const token = cookies(req)[COOKIE]
    const session = token ? this.sessions.get(token) : undefined
    if (!token || !session) return
    session.lastSeen = Date.now()
    return [token, session]
  }
  private async auth(req: IncomingMessage, res: ServerResponse) {
    try {
      const path = new URL(req.url ?? '/', 'http://x').pathname
      if (req.method === 'GET' && path === '/auth/me') {
        const current = this.current(req)
        if (!current) {
          json(res, 401, { authenticated: false })
          return
        }
        const account = this.registry.accounts.find(
          v => v.id === current[1].accountId,
        )
        json(res, 200, {
          authenticated: true,
          guest: current[1].guest,
          username: account?.username ?? '游客',
          audience: account?.audience ?? 'patient',
        })
        return
      }
      if (req.method === 'POST' && path === '/auth/register') {
        const input = await body(req)
        const username = asText(input.username).trim().toLowerCase()
        const password = asText(input.password)
        if (!/^[\p{L}\p{N}_.-]{3,32}$/u.test(username))
          throw new Error('用户名需为 3 至 32 个字符')
        if (password.length < 8 || password.length > 128)
          throw new Error('密码需为 8 至 128 个字符')
        if (this.registry.accounts.some(v => v.username === username))
          throw new Error('用户名已存在')
        const salt = randomBytes(16).toString('hex'),
          recoverySalt = randomBytes(16).toString('hex'),
          code = recoveryCode()
        const account: Account = {
          id: randomUUID(),
          username,
          audience: input.audience === 'doctor' ? 'doctor' : 'patient',
          salt,
          passwordHash: await hashSecret(password, salt),
          recoverySalt,
          recoveryHash: await hashSecret(code, recoverySalt),
          createdAt: new Date().toISOString(),
        }
        this.registry.accounts.push(account)
        await this.save()
        const token = randomBytes(32).toString('base64url')
        this.sessions.set(token, {
          accountId: account.id,
          guest: false,
          lastSeen: Date.now(),
        })
        this.setCookie(res, token)
        json(res, 201, { ok: true, recoveryCode: code })
        return
      }
      if (req.method === 'POST' && path === '/auth/login') {
        const input = await body(req)
        const account = this.registry.accounts.find(
          v =>
            v.username ===
            asText(input.username).trim().toLowerCase(),
        )
        if (
          !account ||
          !equalHash(
            await hashSecret(asText(input.password), account.salt),
            account.passwordHash,
          )
        )
          throw new Error('用户名或密码不正确')
        const token = randomBytes(32).toString('base64url')
        this.sessions.set(token, {
          accountId: account.id,
          guest: false,
          lastSeen: Date.now(),
        })
        this.setCookie(res, token)
        json(res, 200, { ok: true })
        return
      }
      if (req.method === 'POST' && path === '/auth/guest') {
        const token = randomBytes(32).toString('base64url'),
          accountId = `guest-${randomUUID()}`
        this.sessions.set(token, {
          accountId,
          guest: true,
          lastSeen: Date.now(),
        })
        this.setCookie(res, token)
        json(res, 201, { ok: true })
        return
      }
      if (req.method === 'POST' && path === '/auth/recover') {
        const input = await body(req)
        const account = this.registry.accounts.find(
          v =>
            v.username ===
            asText(input.username).trim().toLowerCase(),
        )
        if (
          !account ||
          !equalHash(
            await hashSecret(
              asText(input.recoveryCode),
              account.recoverySalt,
            ),
            account.recoveryHash,
          )
        )
          throw new Error('恢复信息不正确')
        const password = asText(input.password)
        if (password.length < 8 || password.length > 128)
          throw new Error('密码需为 8 至 128 个字符')
        const code = await rotateCredentials(account, password)
        await this.save()
        json(res, 200, { ok: true, recoveryCode: code })
        return
      }
      if (req.method === 'POST' && path === '/auth/credentials') {
        const current = this.current(req)
        if (!current || current[1].guest)
          throw new Error('请先登录持久账号')
        const account = this.registry.accounts.find(
          value => value.id === current[1].accountId,
        )
        const input = await body(req)
        if (
          !account ||
          !equalHash(
            await hashSecret(asText(input.currentPassword), account.salt),
            account.passwordHash,
          )
        )
          throw new Error('当前密码不正确')
        const password = asText(input.password)
        if (password.length < 8 || password.length > 128)
          throw new Error('新密码需为 8 至 128 个字符')
        const code = await rotateCredentials(account, password)
        await this.save()
        for (const [token, session] of this.sessions) {
          if (session.accountId === account.id && token !== current[0])
            this.sessions.delete(token)
        }
        json(res, 200, { ok: true, recoveryCode: code })
        return
      }
      if (req.method === 'POST' && path === '/auth/logout') {
        const current = this.current(req)
        if (current) {
          this.sessions.delete(current[0])
          if (current[1].guest) await this.stopHost(current[1].accountId, true)
        }
        res.setHeader(
          'Set-Cookie',
          `${COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0`,
        )
        json(res, 200, { ok: true })
        return
      }
      json(res, 404, { error: '接口不存在' })
    } catch (error) {
      json(res, 400, { error: safeMessage(error) })
    }
  }
  private async route(req: IncomingMessage, res: ServerResponse) {
    const current = this.current(req)
    if (!current) {
      const html = await readFile(
        new URL('../public/login.html', import.meta.url),
      )
      res.writeHead(200, {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-store',
      })
      res.end(html)
      return
    }
    try {
      const host = await this.ensureHost(current[1])
      this.proxy(req, res, host.port)
    } catch (error) {
      json(res, 503, { error: `健康工作台启动失败：${safeMessage(error)}` })
    }
  }
  private proxy(req: IncomingMessage, res: ServerResponse, port: number) {
    const headers = { ...req.headers }
    delete headers.cookie
    headers.host = `127.0.0.1:${port}`
    if (headers.origin !== undefined)
      headers.origin = `http://127.0.0.1:${port}`
    const upstream = httpRequest(
      { host: '127.0.0.1', port, path: req.url, method: req.method, headers },
      (reply) => {
        res.writeHead(reply.statusCode ?? 502, reply.headers)
        reply.pipe(res)
      },
    )
    upstream.on('error', (error) => {
      if (!res.headersSent)
        json(res, 502, { error: `服务暂时不可用：${error.message}` })
      else res.destroy(error)
    })
    req.pipe(upstream)
  }
  private async upgrade(req: IncomingMessage, socket: Duplex, head: Buffer) {
    const current = this.current(req)
    if (!current) {
      socket.destroy()
      return
    }
    const host = await this.ensureHost(current[1])
    const net = await import('node:net')
    const upstream = net.connect(host.port, '127.0.0.1', () => {
      const headers = Object.entries({
        ...req.headers,
        host: `127.0.0.1:${host.port}`,
        origin: `http://127.0.0.1:${host.port}`,
      })
        .filter(([key]) => key.toLowerCase() !== 'cookie')
        .map(
          ([key, value]) =>
            `${key}: ${Array.isArray(value) ? value.join(', ') : (value ?? '')}`,
        )
        .join('\r\n')
      upstream.write(
        `${req.method ?? 'GET'} ${req.url ?? '/api'} HTTP/${req.httpVersion}\r\n${headers}\r\n\r\n`,
      )
      if (head.length) upstream.write(head)
      socket.pipe(upstream).pipe(socket)
    })
    upstream.on('error', () => socket.destroy())
  }
  private accountDir(session: LoginSession) {
    return join(
      this.config.dataDir,
      session.guest ? 'guests' : 'accounts',
      session.accountId,
    )
  }
  private async prepareProfileModules(dshHome: string) {
    const modules = join(dshHome, 'profiles', 'node_modules')
    const profileDependencies = join(
      this.config.rootDir,
      'packages/gerclaw/profile-bundle/node_modules',
    )
    await mkdir(modules, { recursive: true })
    for (const packageName of CHILD_PLUGIN_PACKAGES) {
      const target = join(
        profileDependencies,
        ...packageName.split('/'),
      )
      const link = join(modules, ...packageName.split('/'))
      await mkdir(join(link, '..'), { recursive: true })
      try {
        const stat = await lstat(link)
        if (!stat.isSymbolicLink())
          throw new Error(`插件目录冲突：${packageName}`)
        await unlink(link)
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
      }
      await symlink(target, link, 'dir')
    }
  }
  private async freePort() {
    return new Promise<number>((resolve, reject) => {
      const server = createServer()
      server.once('error', reject)
      server.listen(0, '127.0.0.1', () => {
        const address = server.address()
        const port = typeof address === 'object' && address ? address.port : 0
        server.close((error) => {
          if (error) reject(error)
          else resolve(port)
        })
      })
    })
  }
  private async ensureHost(session: LoginSession): Promise<Host> {
    const starting = this.hostStarts.get(session.accountId)
    if (starting) {
      const host = await starting
      host.lastSeen = Date.now()
      return host
    }
    const existing = this.hosts.get(session.accountId)
    if (existing && existing.process.exitCode === null) {
      existing.lastSeen = Date.now()
      return existing
    }
    const start = this.startHost(session)
    this.hostStarts.set(session.accountId, start)
    try {
      return await start
    } catch (error) {
      await this.stopHost(session.accountId, session.guest)
      throw error
    } finally {
      if (this.hostStarts.get(session.accountId) === start)
        this.hostStarts.delete(session.accountId)
    }
  }
  private async startHost(session: LoginSession): Promise<Host> {
    const dir = this.accountDir(session)
    await mkdir(dir, { recursive: true })
    const accountDataDir = join(dir, 'data')
    await mkdir(accountDataDir, { recursive: true })
    const workspaceDir = join(accountDataDir, 'workspace')
    await mkdir(workspaceDir, { recursive: true })
    const childDshHome = join(dir, 'dsh')
    await syncControlledDirectory(
      join(
        this.config.rootDir,
        'packages/gerclaw/profile-bundle/presets/gerclaw',
      ),
      join(childDshHome, '.agent-presets/gerclaw'),
      'GerClaw 运行预设',
      true,
    )
    await this.prepareProfileModules(childDshHome)
    const port = await this.freePort()
    const account = this.registry.accounts.find(
      v => v.id === session.accountId,
    )
    const child = spawn(
      process.execPath,
      [
        join(this.config.rootDir, 'apps/cli/lib/bin.js'),
        '--profile',
        'web',
        '--patch',
        this.config.childPatch,
        '--',
        '--no-open',
      ],
      {
        cwd: this.config.rootDir,
        stdio: ['ignore', 'ignore', 'pipe'],
        env: {
          ...process.env,
          DSH_HOME: childDshHome,
          GERCLAW_ACCOUNT_DATA_DIR: accountDataDir,
          GERCLAW_ACCOUNT_ID: session.accountId,
          GERCLAW_AUDIENCE: account?.audience ?? 'patient',
          GERCLAW_ROOT_DIR: this.config.rootDir,
          GERCLAW_HOST_PORT: String(port),
          MEMORIX_DATA_DIR: join(dir, 'memorix'),
          DSH_TELEMETRY_DISABLED: '1',
        },
      },
    )
    let diagnostic = ''
    child.stderr.setEncoding('utf8')
    child.stderr.on('data', (chunk: string) => {
      diagnostic = `${diagnostic}${chunk}`.slice(-16_384)
      if (process.env.GERCLAW_DIAGNOSTICS === '1') {
        process.stderr.write(
          chunk.replace(/(?:sk-|Bearer\s+)[A-Za-z0-9._-]+/g, '[已隐藏]'),
        )
      }
    })
    const host = {
      process: child,
      port,
      lastSeen: Date.now(),
      guest: session.guest,
    }
    this.hosts.set(session.accountId, host)
    child.once('exit', () => {
      if (this.hosts.get(session.accountId)?.process === child)
        this.hosts.delete(session.accountId)
    })
    const deadline = Date.now() + 45_000
    while (Date.now() < deadline) {
      if (child.exitCode !== null) {
        if (process.env.GERCLAW_DIAGNOSTICS === '1') {
          console.error(
            diagnostic
              .replace(/(?:sk-|Bearer\s+)[A-Za-z0-9._-]+/g, '[已隐藏]')
              .slice(-4_000),
          )
        }
        throw new Error('账号服务未能启动')
      }
      let ready = false
      try {
        ready = (
          await fetch(`http://127.0.0.1:${port}/gerclaw/api/bootstrap`)
        ).ok
      } catch {}
      if (ready) {
        const workspace = await fetch(
          `http://127.0.0.1:${port}/api/workspace.create`,
          {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({
              type: 'client-request',
              rpcId: randomUUID(),
              method: 'workspace.create',
              payload: { path: workspaceDir },
            }),
          },
        )
        if (!workspace.ok)
          throw new Error('账号默认工作区创建失败')
        const result = await workspace.json() as {
          result?: { ok?: boolean; error?: { message?: string } }
        }
        if (result.result?.ok !== true)
          throw new Error(
            result.result?.error?.message ?? '账号默认工作区创建失败',
          )
        const sidebar = await fetch(
          `http://127.0.0.1:${port}/sidebar/api/settings.update`,
          {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({
              patch: {
                openByDefault: true,
                defaultWidthPercent: 25,
                autoOpenSubagent: false,
                autoOpenJobs: false,
                agentTerminalTools: false,
                bottomPanelAutoTerminal: false,
                interceptOpenPath: false,
                browserInterceptLinks: false,
                tabsEnabled: {
                  editor: false,
                  git: false,
                  subagent: false,
                  sidechat: false,
                  terminal: false,
                  browser: false,
                  diff: false,
                  'gerclaw-artifacts': true,
                },
              },
            }),
          },
        )
        if (!sidebar.ok)
          throw new Error('账号产物栏初始化失败')
        const sidebarResult = await sidebar.json() as { ok?: boolean }
        if (sidebarResult.ok !== true)
          throw new Error('账号产物栏初始化失败')
        return host
      }
      await new Promise(resolve => setTimeout(resolve, 250))
    }
    await this.stopHost(session.accountId, session.guest)
    throw new Error('账号服务启动超时')
  }
  private async stopHost(accountId: string, removeData: boolean) {
    const host = this.hosts.get(accountId)
    this.hosts.delete(accountId)
    if (host && host.process.exitCode === null) {
      host.process.kill('SIGTERM')
      await Promise.race([
        new Promise<void>(resolve =>
          host.process.once('exit', () => {
            resolve()
          }),
        ),
        new Promise<void>(resolve =>
          setTimeout(() => {
            host.process.kill('SIGKILL')
            resolve()
          }, 3000),
        ),
      ])
    }
    if (removeData)
      await rm(join(this.config.dataDir, 'guests', accountId), {
        recursive: true,
        force: true,
      })
  }
  private async reap() {
    const now = Date.now(),
      idle = this.config.idleMs ?? THIRTY_MINUTES
    for (const [token, session] of this.sessions)
      if (now - session.lastSeen > idle) {
        this.sessions.delete(token)
        await this.stopHost(session.accountId, session.guest)
      }
    for (const [id, host] of this.hosts)
      if (
        now - host.lastSeen > idle &&
        ![...this.sessions.values()].some(v => v.accountId === id)
      )
        await this.stopHost(id, host.guest)
  }
  private async sweepGuests() {
    await rm(join(this.config.dataDir, 'guests'), {
      recursive: true,
      force: true,
    })
    await mkdir(join(this.config.dataDir, 'guests'), { recursive: true })
  }
}
export default GerclawTenantGateway
