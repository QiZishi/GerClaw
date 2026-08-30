import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { FiberState, type Context } from '@deepseek-ai/cordis'
import { boot } from '@deepseek-ai/dsh-app-boot'
import { describe, expect, it } from 'vitest'

const repoRoot = join(import.meta.dirname, '../../../..')
const pluginUrl = (name: string): string => pathToFileURL(
  join(repoRoot, 'packages/gerclaw', name, 'lib/index.js'),
).href

type HotplugCase = {
  id: string
  packageName: string
  service: string
  config?: Record<string, unknown>
  dependencies?: string
  expectRegistrations?: boolean
}

const entryById = (ctx: Context, id: string) => {
  const entry = [...ctx.loader.entries()].find(candidate => candidate.options.id === id)
  if (entry === undefined) throw new Error(`真实 Loader 树缺少 ${id}`)
  return entry
}

const dependencySource = (body: string): string => [
  'export function apply(ctx) {',
  '  const state = globalThis[Symbol.for("gerclaw.test.all-service-hotplug")]',
  body,
  '}',
  '',
].join('\n')

const standalone: HotplugCase[] = [
  { id: 'cga', packageName: 'cga', service: 'gerclawCga' },
  { id: 'medication-review', packageName: 'medication-review', service: 'gerclawMedicationReview' },
  { id: 'health-profile', packageName: 'health-profile', service: 'gerclawHealthProfile' },
  { id: 'chronic-care', packageName: 'chronic-care', service: 'gerclawChronicCare' },
  { id: 'companion', packageName: 'companion', service: 'gerclawCompanion' },
  { id: 'risk-alert', packageName: 'risk-alert', service: 'gerclawRiskAlert' },
  { id: 'medical-evidence', packageName: 'medical-evidence-public', service: 'gerclawMedicalEvidence' },
]

describe('every replaceable GerClaw service through the real Loader', () => {
  it.each(standalone)('$id unloads, cleans its consumer, and reloads once', async (testCase) => {
    await verifyHotplug(testCase)
  })

  it.each<HotplugCase>([
    {
      id: 'document-parser',
      packageName: 'document-parser-mineru',
      service: 'gerclawDocumentParser',
      config: { timeoutMs: 10_000 },
      dependencies: dependencySource('  ctx.provide("credentials", { resolve: async () => undefined })'),
    },
    {
      id: 'health-repository',
      packageName: 'health-repository-storage',
      service: 'healthRepository',
      dependencies: dependencySource([
        '  const table = { get: () => undefined, put: async () => {}, entries: () => [][Symbol.iterator](), delete: async () => {} }',
        '  ctx.provide("storageDomain", { open: async () => {',
        '    state.registrations += 1',
        '    return { table: () => table, close: async () => { state.registrations -= 1 } }',
        '  } })',
      ].join('\n')),
      expectRegistrations: true,
    },
    {
      id: 'artifacts',
      packageName: 'artifact-local',
      service: 'gerclawArtifacts',
      config: { dataDir: tmpdir(), accountId: 'loader-test' },
      dependencies: dependencySource([
        '  ctx.provide("healthRepository", { get: () => undefined, put: async () => {}, list: () => [] })',
        '  ctx.provide("workspaceRegistry", {})',
        '  ctx.provide("fs", {})',
      ].join('\n')),
    },
    {
      id: 'prescription',
      packageName: 'prescription',
      service: 'gerclawPrescription',
      dependencies: dependencySource([
        '  ctx.provide("subagents", {})',
        '  ctx.provide("gerclawMedicationReview", {})',
        '  ctx.provide("gerclawRag", {})',
      ].join('\n')),
    },
    {
      id: 'task-runtime',
      packageName: 'task-runtime-local',
      service: 'gerclawTasks',
      dependencies: dependencySource([
        '  const attachController = () => { state.registrations += 1; return () => { state.registrations -= 1 } }',
        '  ctx.provide("jobs", { attachController })',
        '  ctx.provide("sessionProjections", { register: () => () => {}, stateOf: () => undefined })',
        '  for (const name of ["sessions", "subagents", "healthRepository", "gerclawArtifacts", "gerclawCga", "gerclawMedicationReview", "gerclawMedicalEvidence", "gerclawHealthProfile", "gerclawChronicCare", "gerclawRiskAlert", "gerclawCompanion", "gerclawRag"]) ctx.provide(name, {})',
      ].join('\n')),
      expectRegistrations: true,
    },
    {
      id: 'tenant-host',
      packageName: 'tenant-host-local',
      service: 'gerclawTenantHost',
      config: {
        rootDir: repoRoot,
        dataDir: join(tmpdir(), 'gerclaw-tenant-host-loader-test'),
        cliPath: join(repoRoot, 'apps/cli/lib/index.js'),
        profilePackageSpecs: [],
        forwardEnv: [],
        idleMs: 60_000,
        startupTimeoutMs: 1_000,
      },
      dependencies: dependencySource([
        '  ctx.provide("tenantRuntime", {})',
        '  ctx.provide("subprocess", {})',
        '  ctx.provide("timer", {})',
      ].join('\n')),
    },
    {
      id: 'tenant-store',
      packageName: 'tenant-store',
      service: 'tenantSessionStore',
      dependencies: dependencySource([
        '  const table = { get: () => undefined, put: async () => {} }',
        '  ctx.provide("storageDomain", { open: async () => {',
        '    state.registrations += 1',
        '    return { table: () => table, close: async () => { state.registrations -= 1 } }',
        '  } })',
      ].join('\n')),
      expectRegistrations: true,
    },
    {
      id: 'tenant-gateway',
      packageName: 'tenant-gateway',
      service: 'gerclawTenantGateway',
      config: { rootDir: repoRoot },
      dependencies: dependencySource([
        '  const register = () => { state.registrations += 1; return () => { state.registrations -= 1 } }',
        '  ctx.provide("webServer", { register, registerFallback: register, registerUpgrade: register })',
        '  ctx.provide("gerclawAuth", {})',
        '  ctx.provide("gerclawTenantHost", {})',
        '  ctx.provide("multiTenant", {})',
      ].join('\n')),
      expectRegistrations: true,
    },
    {
      id: 'app',
      packageName: 'client',
      service: 'gerclawApp',
      config: { rootDir: repoRoot, dataDir: join(tmpdir(), 'gerclaw-app-loader-test'), accountId: 'loader-test' },
      dependencies: dependencySource([
        '  const register = () => { state.registrations += 1; return () => { state.registrations -= 1 } }',
        '  ctx.provide("webServer", { register })',
        '  ctx.provide("tools", { register })',
        '  ctx.provide("systemPrompt", { section: () => () => {} })',
        '  ctx.provide("sessionProjections", { register: () => () => {}, stateOf: () => undefined })',
        '  ctx.provide("workspaceRegistry", { create: async () => {} })',
        '  for (const name of ["sessions", "agents", "subagents", "healthRepository", "gerclawArtifacts", "gerclawTasks", "gerclawDocumentParser", "gerclawMedicalEvidence", "gerclawPrescription", "gerclawRag"]) ctx.provide(name, {})',
      ].join('\n')),
      expectRegistrations: true,
    },
  ])('$id cascades on dependency loss and restores without duplicate resources', async (testCase) => {
    await verifyHotplug(testCase)
  })
})

async function verifyHotplug(testCase: HotplugCase): Promise<void> {
  const dir = await mkdtemp(join(tmpdir(), `gerclaw-${testCase.id}-hotplug-`))
  const configPath = join(dir, 'cordis.yml')
  const dependencyPath = join(dir, 'dependencies.mjs')
  const consumerPath = join(dir, 'consumer.mjs')
  const failingPath = join(dir, 'failing.mjs')
  const marker = Symbol.for('gerclaw.test.all-service-hotplug')
  const state = { consumers: 0, registrations: 0 }
  Reflect.set(globalThis, marker, state)
  await writeFile(consumerPath, dependencySource([
    '  state.consumers += 1',
    '  ctx.effect(() => () => { state.consumers -= 1 })',
  ].join('\n')))
  await writeFile(failingPath, 'export function apply() { throw new Error("candidate apply failed") }\n')
  const lines: string[] = []
  if (testCase.dependencies !== undefined) {
    await writeFile(dependencyPath, testCase.dependencies)
    lines.push('- id: dependencies', `  name: ${JSON.stringify(pathToFileURL(dependencyPath).href)}`)
  }
  lines.push(
    `- id: ${testCase.id}`,
    `  name: ${JSON.stringify(pluginUrl(testCase.packageName))}`,
  )
  const resolvedConfig = testCase.config === undefined ? undefined : { ...testCase.config }
  if (testCase.packageName === 'artifact-local') resolvedConfig!.dataDir = dir
  if (testCase.packageName === 'tenant-host-local') resolvedConfig!.dataDir = join(dir, 'tenant-data')
  if (testCase.packageName === 'client') resolvedConfig!.dataDir = join(dir, 'app-data')
  if (resolvedConfig !== undefined) lines.push(`  config: ${JSON.stringify(resolvedConfig)}`)
  lines.push(
    '- id: consumer',
    `  name: ${JSON.stringify(pathToFileURL(consumerPath).href)}`,
    `  inject: [${testCase.service}]`,
    '',
  )
  await writeFile(configPath, lines.join('\n'))
  const ctx = await boot(`gerclaw-${testCase.id}-hotplug-test`, configPath)
  try {
    const provider = entryById(ctx, testCase.id)
    const consumer = entryById(ctx, 'consumer')
    const toggle = testCase.dependencies === undefined ? provider : entryById(ctx, 'dependencies')
    expect(provider.fiber?.state).toBe(FiberState.ACTIVE)
    expect(consumer.fiber?.state).toBe(FiberState.ACTIVE)
    expect(ctx.get(testCase.service)).toBeDefined()
    expect(state.consumers).toBe(1)
    if (testCase.expectRegistrations === true) expect(state.registrations).toBeGreaterThan(0)

    await ctx.loader.update(toggle.id, { disabled: true })
    await ctx.loader.await()
    if (testCase.dependencies === undefined) expect(provider.fiber).toBeUndefined()
    else expect(provider.fiber?.state).toBe(FiberState.PENDING)
    expect(consumer.fiber?.state).toBe(FiberState.PENDING)
    expect(ctx.get(testCase.service)).toBeUndefined()
    expect(state.consumers).toBe(0)
    expect(state.registrations).toBe(0)

    await ctx.loader.update(toggle.id, { disabled: false })
    await ctx.loader.await()
    expect(provider.fiber?.state).toBe(FiberState.ACTIVE)
    expect(consumer.fiber?.state).toBe(FiberState.ACTIVE)
    expect(ctx.get(testCase.service)).toBeDefined()
    expect(state.consumers).toBe(1)
    if (testCase.expectRegistrations === true) expect(state.registrations).toBeGreaterThan(0)

    const restoredRegistrations = state.registrations
    await expect(provider.update({ name: pathToFileURL(failingPath).href }))
      .rejects.toThrow('candidate apply failed')
    expect(provider.options.name).toBe(pluginUrl(testCase.packageName))
    expect(provider.fiber?.state).toBe(FiberState.ACTIVE)
    expect(consumer.fiber?.state).toBe(FiberState.ACTIVE)
    expect(ctx.get(testCase.service)).toBeDefined()
    expect(state.consumers).toBe(1)
    expect(state.registrations).toBe(restoredRegistrations)
  } finally {
    await ctx.fiber.dispose()
    expect(state.consumers).toBe(0)
    expect(state.registrations).toBe(0)
    Reflect.deleteProperty(globalThis, marker)
    await rm(dir, { recursive: true, force: true })
  }
}
