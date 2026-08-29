/** Authenticated HTTP/WebSocket gateway consuming Cordis tenant services. */
import { readFile } from 'node:fs/promises'
import { request as httpRequest, type IncomingMessage, type ServerResponse } from 'node:http'
import { join } from 'node:path'
import type { Duplex } from 'node:stream'
import { Context, Service } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-host-webserver'
import type { TenantPrincipal } from 'dsh-multi-tenant'
import type { GerclawLoginSession } from '@gerclaw/auth'
import type {} from '@gerclaw/tenant-host'

const COOKIE = 'gerclaw_session'

export interface TenantGatewayConfig {
  rootDir: string
}

const json = (res: ServerResponse, status: number, value: unknown): void => {
  const payload = JSON.stringify(value)
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  })
  res.end(payload)
}

const readBody = async (req: IncomingMessage): Promise<Record<string, unknown>> => {
  const chunks: Buffer[] = []
  let total = 0
  for await (const chunk of req as AsyncIterable<Uint8Array>) {
    const part = Buffer.from(chunk)
    total += part.byteLength
    if (total > 64 * 1024) throw new Error('请求内容过大')
    chunks.push(part)
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}') as Record<string, unknown>
}

const text = (value: unknown): string => typeof value === 'string' ? value : ''

const cookieValue = (req: IncomingMessage): string | undefined => {
  for (const part of (req.headers.cookie ?? '').split(';')) {
    const [name, ...rest] = part.trim().split('=')
    if (name === COOKIE) return rest.join('=')
  }
  return undefined
}

const setCookie = (res: ServerResponse, token: string): void => {
  res.setHeader(
    'Set-Cookie',
    `${COOKIE}=${token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000`,
  )
}

const clearCookie = (res: ServerResponse): void => {
  res.setHeader(
    'Set-Cookie',
    `${COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0`,
  )
}

const safeMessage = (error: unknown): string => error instanceof Error ? error.message : '操作失败'

const principalOf = (session: GerclawLoginSession): TenantPrincipal => ({
  tenantId: 'gerclaw',
  userId: session.accountId,
})

export class GerclawTenantGateway extends Service {
  static inject = ['webServer', 'gerclawAuth', 'gerclawTenantHost', 'multiTenant']

  constructor(ctx: Context, private readonly config: TenantGatewayConfig) {
    super(ctx, 'gerclawTenantGateway')
  }

  protected [Service.init](): void {
    const serveIcon = async (_req: IncomingMessage, res: ServerResponse): Promise<void> => {
      const data = await readFile(join(this.config.rootDir, 'icon.png'))
      res.writeHead(200, {
        'Content-Type': 'image/png',
        'Cache-Control': 'public,max-age=3600',
      })
      res.end(data)
    }
    this.ctx.effect(() => this.ctx.webServer.register({
      kind: 'prefix',
      path: '/auth',
      handler: (req, res) => this.auth(req, res),
    }), 'gerclaw.gateway.auth')
    this.ctx.effect(() => this.ctx.webServer.register({
      kind: 'exact',
      path: '/brand-icon.png',
      handler: serveIcon,
    }), 'gerclaw.gateway.brand-icon')
    this.ctx.effect(() => this.ctx.webServer.register({
      kind: 'exact',
      path: '/favicon.ico',
      handler: serveIcon,
    }), 'gerclaw.gateway.favicon')
    this.ctx.effect(
      () => this.ctx.webServer.registerFallback((req, res) => this.route(req, res)),
      'gerclaw.gateway.fallback',
    )
    for (const path of [
      '/api/events.mux',
      '/api/events.host',
      '/gerclaw/api/voice/asr-stream',
      '/sidebar/ws/agent-terminals',
    ]) {
      this.ctx.effect(() => this.ctx.webServer.registerUpgrade({
        path,
        handler: (req, socket, head) => this.upgrade(req, socket, head),
      }), `gerclaw.gateway.upgrade:${path}`)
    }
  }

  private current(req: IncomingMessage): { token: string; session: GerclawLoginSession } | undefined {
    const token = cookieValue(req)
    const session = this.ctx.gerclawAuth.verify(token)
    return token === undefined || session === undefined ? undefined : { token, session }
  }

  private async publishLogin(
    res: ServerResponse,
    token: string,
    session: GerclawLoginSession,
    payload: Record<string, unknown>,
    status = 200,
  ): Promise<void> {
    await this.ctx.multiTenant.claimSession(token, principalOf(session))
    setCookie(res, token)
    json(res, status, payload)
  }

  private async auth(req: IncomingMessage, res: ServerResponse): Promise<void> {
    try {
      const path = new URL(req.url ?? '/', 'http://gerclaw.local').pathname
      if (req.method === 'GET' && path === '/auth/me') {
        const current = this.current(req)
        if (current === undefined) {
          json(res, 401, { authenticated: false })
          return
        }
        await this.ctx.multiTenant.assertSessionAccess(principalOf(current.session), current.token)
        json(res, 200, {
          authenticated: true,
          guest: current.session.guest,
          username: current.session.username,
          audience: current.session.audience,
        })
        return
      }
      if (req.method === 'POST' && path === '/auth/register') {
        const input = await readBody(req)
        const result = await this.ctx.gerclawAuth.register(
          text(input.username),
          text(input.password),
          input.audience === 'doctor' ? 'doctor' : 'patient',
        )
        const session = this.ctx.gerclawAuth.verify(result.token)
        if (session === undefined) throw new Error('登录会话创建失败')
        await this.publishLogin(
          res,
          result.token,
          session,
          { ok: true, recoveryCode: result.recoveryCode },
          201,
        )
        return
      }
      if (req.method === 'POST' && path === '/auth/login') {
        const input = await readBody(req)
        const result = await this.ctx.gerclawAuth.login(text(input.username), text(input.password))
        const session = this.ctx.gerclawAuth.verify(result.token)
        if (session === undefined) throw new Error('登录会话创建失败')
        await this.publishLogin(res, result.token, session, { ok: true })
        return
      }
      if (req.method === 'POST' && path === '/auth/guest') {
        const result = this.ctx.gerclawAuth.guest()
        await this.publishLogin(res, result.token, result.session, { ok: true }, 201)
        return
      }
      if (req.method === 'POST' && path === '/auth/recover') {
        const input = await readBody(req)
        const code = await this.ctx.gerclawAuth.recover(
          text(input.username),
          text(input.recoveryCode),
          text(input.password),
        )
        json(res, 200, { ok: true, recoveryCode: code })
        return
      }
      if (req.method === 'POST' && path === '/auth/credentials') {
        const current = this.current(req)
        if (current === undefined || current.session.guest) throw new Error('请先登录持久账号')
        await this.ctx.multiTenant.assertSessionAccess(principalOf(current.session), current.token)
        const input = await readBody(req)
        const code = await this.ctx.gerclawAuth.changePassword(
          current.session.accountId,
          text(input.currentPassword),
          text(input.password),
          current.token,
        )
        json(res, 200, { ok: true, recoveryCode: code })
        return
      }
      if (req.method === 'POST' && path === '/auth/logout') {
        const current = this.current(req)
        if (current !== undefined) {
          this.ctx.gerclawAuth.revoke(current.token)
          if (current.session.guest) {
            await this.ctx.gerclawTenantHost.disposePrincipal(principalOf(current.session))
          }
        }
        clearCookie(res)
        json(res, 200, { ok: true })
        return
      }
      json(res, 404, { error: '接口不存在' })
    } catch (error) {
      json(res, 400, { error: safeMessage(error) })
    }
  }

  private async route(req: IncomingMessage, res: ServerResponse): Promise<void> {
    const current = this.current(req)
    if (current === undefined) {
      const html = await readFile(new URL('../public/login.html', import.meta.url))
      res.writeHead(200, {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-store',
      })
      res.end(html)
      return
    }
    try {
      const principal = principalOf(current.session)
      await this.ctx.multiTenant.assertSessionAccess(principal, current.token)
      const endpoint = await this.ctx.gerclawTenantHost.ensure({
        principal,
        guest: current.session.guest,
        audience: current.session.audience,
      })
      this.proxy(req, res, endpoint.port)
    } catch (error) {
      json(res, 503, { error: `健康工作台启动失败：${safeMessage(error)}` })
    }
  }

  private proxy(req: IncomingMessage, res: ServerResponse, port: number): void {
    const headers = { ...req.headers, host: `127.0.0.1:${String(port)}` }
    delete headers.cookie
    if (headers.origin !== undefined) headers.origin = `http://127.0.0.1:${String(port)}`
    const upstream = httpRequest({
      host: '127.0.0.1',
      port,
      path: req.url,
      method: req.method,
      headers,
    }, (reply) => {
      res.writeHead(reply.statusCode ?? 502, reply.headers)
      reply.pipe(res)
    })
    const dispose = this.ctx.effect(() => () => upstream.destroy(), 'gerclaw.gateway.http-upstream')
    res.once('close', () => { void dispose() })
    upstream.once('error', (error) => {
      if (!res.headersSent) json(res, 502, { error: `服务暂时不可用：${error.message}` })
      else res.destroy(error)
    })
    req.pipe(upstream)
  }

  private async upgrade(req: IncomingMessage, socket: Duplex, head: Buffer): Promise<void> {
    const current = this.current(req)
    if (current === undefined) {
      socket.destroy()
      return
    }
    try {
      const principal = principalOf(current.session)
      await this.ctx.multiTenant.assertSessionAccess(principal, current.token)
      const endpoint = await this.ctx.gerclawTenantHost.ensure({
        principal,
        guest: current.session.guest,
        audience: current.session.audience,
      })
      const { connect } = await import('node:net')
      const upstream = connect(endpoint.port, endpoint.host, () => {
        const forwarded = Object.entries({
          ...req.headers,
          host: `${endpoint.host}:${String(endpoint.port)}`,
          origin: `http://${endpoint.host}:${String(endpoint.port)}`,
        })
          .filter(([key]) => key.toLowerCase() !== 'cookie')
          .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : (value ?? '')}`)
          .join('\r\n')
        upstream.write(
          `${req.method ?? 'GET'} ${req.url ?? '/api'} HTTP/${req.httpVersion}\r\n${forwarded}\r\n\r\n`,
        )
        if (head.byteLength > 0) upstream.write(head)
        socket.pipe(upstream).pipe(socket)
      })
      const dispose = this.ctx.effect(() => () => {
        socket.destroy()
        upstream.destroy()
      }, 'gerclaw.gateway.websocket-upstream')
      socket.once('close', () => { void dispose() })
      upstream.once('error', () => socket.destroy())
    } catch {
      socket.destroy()
    }
  }
}

export default GerclawTenantGateway
