/** Local per-principal DSH Host provider over the native subprocess seam. */
import { connect, createServer, type Socket } from 'node:net'
import { mkdir, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { Context, Service } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/cordis-plugin-timer'
import { initProfile, PROFILE_TEMPLATES, resolveProfileDir } from '@deepseek-ai/dsh-app-boot'
import z from '@deepseek-ai/schemastery'
import type { SubprocessHandle } from '@deepseek-ai/dsh-subprocess'
import type { TenantPrincipal } from 'dsh-multi-tenant'
import { TenantHostRuntime, type TenantHostEndpoint, type TenantHostRequest } from '@gerclaw/tenant-host'

declare module '@deepseek-ai/cordis' {
  interface Context {
    gerclawTenantHostInstance: TenantHostInstance
  }
}

interface TenantHostInstance extends TenantHostEndpoint {
  process: SubprocessHandle
  alive: boolean
  ready: Promise<void>
  disposeScope?: () => Promise<void>
}

export interface LocalTenantHostConfig {
  rootDir: string
  dataDir: string
  cliPath: string
  profilePackageSpecs: string[]
  forwardEnv: string[]
  idleMs: number
  startupTimeoutMs: number
}

const safeId = (value: string): string => {
  if (!/^[A-Za-z0-9-]{1,128}$/.test(value)) throw new Error('账号标识格式无效')
  return value
}

const freePort = (): Promise<number> => new Promise((resolve, reject) => {
  const server = createServer()
  server.once('error', reject)
  server.listen(0, '127.0.0.1', () => {
    const address = server.address()
    const port = typeof address === 'object' && address !== null ? address.port : 0
    server.close((error) => {
      if (error === undefined) resolve(port)
      else reject(error)
    })
  })
})

const explicitEnv = (names: readonly string[]): NodeJS.ProcessEnv => Object.fromEntries(
  names.flatMap((name) => {
    const value = process.env[name]
    return value === undefined ? [] : [[name, value]]
  }),
)

// Per-account profiles are independent pnpm workspaces. Keep their reviewed
// native-build policy aligned with the DSH root before the official plugin
// command resolves the selected community bundles.
const PROFILE_BUILD_POLICY = `packages:
  - .

nodeLinker: hoisted
autoInstallPeers: false

allowBuilds:
  better-sqlite3: true
  node-pty: true
  onnxruntime-node: true
  protobufjs: false
  sharp: true
`

export class LocalTenantHostRuntime extends TenantHostRuntime {
  static inject = ['tenantRuntime', 'subprocess', 'timer']
  static Config: z<LocalTenantHostConfig> = z.object({
    rootDir: z.string().required(),
    dataDir: z.string().required(),
    cliPath: z.string().required(),
    profilePackageSpecs: z.array(z.string()).default([]),
    forwardEnv: z.array(z.string()).default([]),
    idleMs: z.number().min(60_000).default(1_800_000),
    startupTimeoutMs: z.number().min(1_000).default(120_000),
  })

  constructor(ctx: Context, private readonly config: LocalTenantHostConfig) {
    super(ctx)
  }

  protected async [Service.init](): Promise<void> {
    // Guest Hosts are never durable. A process-level interruption can prevent
    // principal disposers from finishing, so the next native Loader activation
    // clears only the dedicated guest root before accepting new principals.
    const guestsRoot = join(this.config.dataDir, 'guests')
    await rm(guestsRoot, { recursive: true, force: true })
    await mkdir(guestsRoot, { recursive: true })
  }

  async ensure(request: TenantHostRequest): Promise<TenantHostEndpoint> {
    const tenant = await this.ctx.tenantRuntime.tenants.ensure(request.principal.tenantId)
    const definition = {
      isolateServices: ['gerclawTenantHostInstance'],
      setup: async ({ ctx, signal }: { ctx: Context; signal: AbortSignal }) => {
        const instance = await this.startPrincipalHost(ctx, request, signal)
        ctx.provide('gerclawTenantHostInstance', instance)
      },
    }
    let scope = await tenant.principals.ensure(request.principal.userId, definition)
    let instance = scope.ctx.gerclawTenantHostInstance
    if (!instance.alive) {
      await scope.dispose()
      scope = await tenant.principals.ensure(request.principal.userId, definition)
      instance = scope.ctx.gerclawTenantHostInstance
    }
    instance.disposeScope = () => scope.dispose()
    try {
      await instance.ready
    } catch (error) {
      await scope.dispose()
      throw error
    }
    instance.lastSeen = Date.now()
    return this.publicEndpoint(instance)
  }

  async disposePrincipal(principal: TenantPrincipal): Promise<void> {
    const tenant = this.ctx.tenantRuntime.tenants.get(principal.tenantId)
    await tenant?.principals.get(principal.userId)?.dispose()
  }

  private async startPrincipalHost(
    ctx: Context,
    request: TenantHostRequest,
    signal: AbortSignal,
  ): Promise<TenantHostInstance> {
    const id = safeId(request.principal.userId)
    const parent = request.guest ? 'guests' : 'accounts'
    const accountDir = join(this.config.dataDir, parent, id)
    const accountDataDir = join(accountDir, 'data')
    const dshHome = join(accountDir, 'dsh')
    await mkdir(accountDataDir, { recursive: true })
    let child: SubprocessHandle | undefined
    let port = 0
    try {
      await this.installProfile(dshHome, signal)
      port = await freePort()
      child = this.ctx.subprocess.spawn({
        argv: [process.execPath, this.config.cliPath, '--profile', 'web', '--', '--no-open'],
        cwd: this.config.rootDir,
        stdio: { stdin: 'ignore', stdout: 'pipe', stderr: 'pipe' },
        graceMs: 3_000,
        env: {
          ...explicitEnv(this.config.forwardEnv),
          DSH_HOME: dshHome,
          DSH_TELEMETRY_DISABLED: '1',
          GERCLAW_ROOT_DIR: this.config.rootDir,
          GERCLAW_ACCOUNT_DATA_DIR: accountDataDir,
          GERCLAW_ACCOUNT_ID: id,
          GERCLAW_AUDIENCE: request.audience,
          GERCLAW_HOST_PORT: String(port),
          MEMORIX_DATA_DIR: join(accountDataDir, 'memorix'),
        },
      })
    } catch (error) {
      child?.terminate()
      await child?.done.catch(() => undefined)
      if (request.guest) await rm(accountDir, { recursive: true, force: true })
      throw error
    }
    const instance: TenantHostInstance = {
      principal: request.principal,
      host: '127.0.0.1',
      port,
      guest: request.guest,
      lastSeen: Date.now(),
      process: child,
      alive: true,
      ready: Promise.resolve(),
    }
    instance.ready = this.waitUntilReady(ctx, instance)
    void child.done.then(() => { instance.alive = false }, () => { instance.alive = false })
    const disposeIdle = this.ctx.interval(() => {
      if (Date.now() - instance.lastSeen >= this.config.idleMs) {
        void instance.disposeScope?.()
      }
    }, Math.min(60_000, this.config.idleMs))
    ctx.effect(() => disposeIdle, 'gerclaw.tenant-host-local.idle')
    ctx.effect(() => async () => {
      instance.alive = false
      child.terminate()
      await child.done.catch(() => undefined)
      await child.waitForExit()
      if (request.guest) await rm(accountDir, { recursive: true, force: true })
    }, 'gerclaw.tenant-host-local.stop')
    return instance
  }

  private async installProfile(dshHome: string, signal: AbortSignal): Promise<void> {
    const profileDir = resolveProfileDir('web', dshHome)
    const webBundles = PROFILE_TEMPLATES.web
    if (webBundles === undefined) throw new Error('DSH Web Profile 模板不存在')
    initProfile(profileDir, webBundles)
    await writeFile(join(profileDir, 'pnpm-workspace.yaml'), PROFILE_BUILD_POLICY, 'utf8')
    const handle = this.ctx.subprocess.spawn({
      argv: [
        process.execPath,
        this.config.cliPath,
        'plugin',
        '--profile',
        'web',
        'add',
        ...this.config.profilePackageSpecs,
        '--prefer-offline',
      ],
      cwd: this.config.rootDir,
      stdio: {
        stdin: 'ignore',
        stdout: { maxBytes: 16_384 },
        stderr: { maxBytes: 16_384 },
      },
      graceMs: 3_000,
      signal,
      env: { DSH_HOME: dshHome },
    })
    const outcome = await handle.done
    if (outcome.exitCode !== 0) {
      const stdout = handle.collected.stdout?.readFrom(0).text.trim()
      const stderr = handle.collected.stderr?.readFrom(0).text.trim()
      if (process.env.GERCLAW_DIAGNOSTICS === '1') {
        if (stdout) process.stderr.write(`[GerClaw profile install stdout]\n${stdout}\n`)
        if (stderr) process.stderr.write(`[GerClaw profile install stderr]\n${stderr}\n`)
      }
      throw new Error('账号运行配置安装失败')
    }
  }

  private waitUntilReady(ctx: Context, instance: TenantHostInstance): Promise<void> {
    const ready = Promise.withResolvers<void>()
    const marker = `127.0.0.1:${String(instance.port)}`
    let settled = false
    let disposeTimeout = (): void => {}
    let disposeProbe = (): void => {}
    const probes = new Set<Socket>()
    const finish = (error?: Error): void => {
      if (settled) return
      settled = true
      disposeTimeout()
      disposeProbe()
      for (const socket of probes) socket.destroy()
      probes.clear()
      if (error === undefined) ready.resolve()
      else ready.reject(error)
    }
    instance.process.stdout?.setEncoding('utf8')
    instance.process.stdout?.on('data', (chunk: string) => {
      if (chunk.includes(marker)) finish()
    })
    let stderrTail = ''
    instance.process.stderr?.setEncoding('utf8')
    instance.process.stderr?.on('data', (chunk: string) => {
      stderrTail = `${stderrTail}${chunk}`.slice(-4_000)
      if (chunk.includes(marker)) finish()
    })
    void instance.process.done.then(
      (outcome) => {
        if (process.env.GERCLAW_DIAGNOSTICS === '1' && stderrTail.length > 0) {
          process.stderr.write(`[GerClaw tenant Host stderr]\n${stderrTail}\n`)
        }
        finish(new Error(`账号 Host 在就绪前退出（${String(outcome.exitCode ?? 'signal')}）`))
      },
      () => { finish(new Error('账号 Host 启动失败')) },
    )
    disposeTimeout = this.ctx.timeout(
      () => { finish(new Error('账号 Host 启动超时')) },
      this.config.startupTimeoutMs,
    )
    ctx.effect(() => disposeTimeout, 'gerclaw.tenant-host-local.readiness-timeout')
    const probe = (): void => {
      if (settled) return
      const socket = connect(instance.port, instance.host)
      probes.add(socket)
      socket.once('connect', () => {
        socket.destroy()
        finish()
      })
      socket.once('error', () => { socket.destroy() })
      socket.once('close', () => { probes.delete(socket) })
    }
    disposeProbe = this.ctx.interval(probe, 50)
    ctx.effect(() => disposeProbe, 'gerclaw.tenant-host-local.readiness-probe')
    probe()
    return ready.promise
  }

  private publicEndpoint(instance: TenantHostInstance): TenantHostEndpoint {
    return {
      principal: instance.principal,
      host: instance.host,
      port: instance.port,
      guest: instance.guest,
      lastSeen: instance.lastSeen,
    }
  }
}

export default LocalTenantHostRuntime
