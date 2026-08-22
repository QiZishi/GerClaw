#!/usr/bin/env node
/** GerClaw launcher: load the target .env and boot the real DSH Web profile. */
import { existsSync, mkdirSync, symlinkSync } from 'node:fs'
import { spawn } from 'node:child_process'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { config as loadEnv } from 'dotenv'

const root = resolve(fileURLToPath(new URL('../../../..', import.meta.url)))
loadEnv({ path: join(root, '.env'), quiet: true })
const required = [
  'AGENT_PRIMARY_API_KEY',
  'AGENT_PRIMARY_URL',
  'AGENT_PRIMARY_MODEL',
]
const missing = required.filter(name => !(process.env[name] ?? '').trim())
if (missing.length) {
  console.error(`GerClaw 无法启动，缺少环境变量：${missing.join(', ')}`)
  process.exit(2)
}
const cli = join(root, 'apps/cli/lib/bin.js')
if (!existsSync(cli)) {
  console.error('GerClaw 尚未构建，请先运行 pnpm build:lib:host。')
  process.exit(2)
}
const gatewayPatch = join(
  root,
  'packages/gerclaw/tenant-gateway/gateway.patch.yml',
)
const gatewayDshHome =
  process.env.DSH_HOME || join(root, '.gerclaw', 'gateway-dsh')
const gatewayModule = join(
  gatewayDshHome,
  'profiles',
  'node_modules',
  '@gerclaw',
  'tenant-gateway',
)
mkdirSync(join(gatewayModule, '..'), { recursive: true })
if (!existsSync(gatewayModule))
  symlinkSync(
    join(root, 'packages/gerclaw/tenant-gateway'),
    gatewayModule,
    'dir',
  )
const dump = process.argv.includes('--dump-config')
const args = ['--profile', 'web', '--patch', gatewayPatch]
if (dump) args.push('--dump-config')
else args.push('--', '--no-open')
const child = spawn(process.execPath, [cli, ...args], {
  cwd: root,
  stdio: 'inherit',
  env: {
    ...process.env,
    DSH_HOME: gatewayDshHome,
    DSH_TELEMETRY_DISABLED: '1',
  },
})
for (const signal of ['SIGINT', 'SIGTERM'] as const)
  process.on(signal, () => child.kill(signal))
child.once('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal)
  else process.exitCode = code ?? 1
})
