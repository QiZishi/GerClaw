#!/usr/bin/env node
/** GerClaw launcher: load the target .env and boot the real DSH Web profile. */
import { existsSync, readFileSync } from 'node:fs'
import { spawn, spawnSync } from 'node:child_process'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { config as loadEnv } from 'dotenv'

const root = resolve(fileURLToPath(new URL('../../../..', import.meta.url)))
loadEnv({ path: join(root, '.env'), quiet: true })
const required = [
  'AGENT_PRIMARY_API_KEY',
  'AGENT_PRIMARY_URL',
  'AGENT_PRIMARY_MODEL',
  'MODEL_ASR_KEY',
  'MODEL_ASR_URL',
  'ASR_MODEL',
  'MODEL_TTS_KEY',
  'MODEL_TTS_URL',
  'TTS_MODEL',
  'SILICONFLOW_API_KEY',
  'SILICONFLOW_URL',
  'EMBEDDING_MODEL',
  'RERANK_MODEL',
  'MINERU_API_KEY',
  'MINERU_URL',
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
const gatewayDshHome =
  process.env.DSH_HOME || join(root, '.gerclaw', 'gateway-dsh')
const gatewayPackage = `link:${join(root, 'packages/gerclaw/tenant-gateway')}`
const runPlugin = (args: string[]): number | null => spawnSync(process.execPath, [
  cli, 'plugin', '--profile', 'web', ...args,
], {
  cwd: root,
  stdio: 'inherit',
  env: { ...process.env, DSH_HOME: gatewayDshHome },
}).status
const install = runPlugin([
  'add',
  'dsh-multi-tenant@0.2.0-rc.3',
  `link:${join(root, 'packages/gerclaw/auth-storage')}`,
  `link:${join(root, 'packages/gerclaw/auth')}`,
  `link:${join(root, 'packages/gerclaw/tenant-store')}`,
  `link:${join(root, 'packages/gerclaw/tenant-host')}`,
  `link:${join(root, 'packages/gerclaw/tenant-host-local')}`,
  gatewayPackage,
  '--offline',
])
if (install !== 0) {
  console.error('GerClaw 网关插件组合安装失败。')
  process.exit(install ?? 2)
}
const manifestPath = join(gatewayDshHome, 'profiles/web/package.json')
const bundles = (JSON.parse(readFileSync(manifestPath, 'utf8')) as {
  dsh?: { profile?: { bundles?: string[] } }
}).dsh?.profile?.bundles ?? []
if (bundles.indexOf('@gerclaw/tenant-gateway') < bundles.indexOf('dsh-multi-tenant')) {
  if (
    runPlugin(['remove', '@gerclaw/tenant-gateway']) !== 0
    || runPlugin(['add', gatewayPackage, '--offline']) !== 0
  ) {
    console.error('GerClaw 网关插件层顺序修复失败。')
    process.exit(2)
  }
}
const dump = process.argv.includes('--dump-config')
const args = ['--profile', 'web']
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
