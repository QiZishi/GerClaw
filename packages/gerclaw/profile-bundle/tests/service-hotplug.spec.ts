import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { FiberState, type Context } from '@deepseek-ai/cordis'
import { boot } from '@deepseek-ai/dsh-app-boot'
import { describe, expect, it } from 'vitest'
import type {} from '@gerclaw/medical-evidence'

const packageEntry = (relative: string): string => pathToFileURL(fileURLToPath(
  new URL(relative, import.meta.url),
)).href

const evidenceProvider = packageEntry('../../medical-evidence-public/lib/index.js')
const taskRuntime = packageEntry('../../task-runtime-local/lib/index.js')
const speechProvider = packageEntry('../../speech-qianwen/lib/index.js')
const voiceConsumer = packageEntry('../../voice/lib/index.js')

const entryById = (ctx: Context, id: string) => {
  const entry = [...ctx.loader.entries()].find(candidate => candidate.options.id === id)
  if (entry === undefined) throw new Error(`真实 Loader 树缺少 ${id}`)
  return entry
}

describe('GerClaw replaceable services through the real Loader', () => {
  it('keeps the task runtime pending while its injected services are absent', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'gerclaw-task-pending-'))
    const config = join(dir, 'cordis.yml')
    await writeFile(config, `- id: task-runtime\n  name: "${taskRuntime}"\n`)
    await expect(boot('gerclaw-task-pending-test', config)).rejects.toThrow(/pending \(waiting for services?:/u)
    await rm(dir, { recursive: true, force: true })
  })

  it('keeps the real voice consumer pending when its injected services are absent', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'gerclaw-voice-pending-'))
    const config = join(dir, 'cordis.yml')
    await writeFile(config, `- id: voice\n  name: "${voiceConsumer}"\n`)
    await expect(boot('gerclaw-voice-pending-test', config)).rejects.toThrow(/pending \(waiting for services?:[\s\S]*speech/u)
    await rm(dir, { recursive: true, force: true })
  })

  it('hot-unplugs and restores the Qianwen speech service through the Loader', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'gerclaw-speech-hotplug-'))
    const config = join(dir, 'cordis.yml')
    const consumer = join(dir, 'consumer.mjs')
    await writeFile(consumer, [
      'export const inject = ["speech"]',
      'export function apply(ctx) {',
      '  ctx.effect(() => {',
      '    globalThis[Symbol.for("gerclaw.test.speech-consumer")] = ctx.speech.info.engine',
      '    return () => { delete globalThis[Symbol.for("gerclaw.test.speech-consumer")] }',
      '  }, "gerclaw.test.speech-consumer")',
      '}',
      '',
    ].join('\n'))
    await writeFile(config, [
      '- id: speech-provider',
      `  name: "${speechProvider}"`,
      '  config:',
      '    asrApiKey: test-asr-key',
      '    asrUrl: wss://example.invalid/asr',
      '    ttsApiKey: test-tts-key',
      '    ttsUrl: wss://example.invalid/tts',
      '    asrModel: qwen3-asr-flash-realtime',
      '    ttsModel: qwen3-tts-instruct-flash-realtime',
      '- id: speech-consumer',
      `  name: "${pathToFileURL(consumer).href}"`,
      '',
    ].join('\n'))
    const ctx = await boot('gerclaw-speech-hotplug-test', config)
    const marker = Symbol.for('gerclaw.test.speech-consumer')
    try {
      const provider = entryById(ctx, 'speech-provider')
      const consumerEntry = entryById(ctx, 'speech-consumer')
      const firstProviderFiber = provider.fiber
      expect(provider.fiber?.state).toBe(FiberState.ACTIVE)
      expect(consumerEntry.fiber?.state).toBe(FiberState.ACTIVE)
      expect(Reflect.get(globalThis, marker)).toBe('qianwen')
      expect(ctx.get('speech')).toBeDefined()

      await ctx.loader.update(provider.id, { disabled: true })
      await ctx.loader.await()
      expect(provider.fiber).toBeUndefined()
      expect(consumerEntry.fiber?.state).toBe(FiberState.PENDING)
      expect(Reflect.get(globalThis, marker)).toBeUndefined()
      expect(ctx.get('speech')).toBeUndefined()

      await ctx.loader.update(provider.id, { disabled: false })
      await ctx.loader.await()
      expect(provider.fiber?.state).toBe(FiberState.ACTIVE)
      expect(consumerEntry.fiber?.state).toBe(FiberState.ACTIVE)
      expect(provider.fiber).not.toBe(firstProviderFiber)
      expect(Reflect.get(globalThis, marker)).toBe('qianwen')
      expect(ctx.get('speech')).toBeDefined()
    } finally {
      await ctx.fiber.dispose()
      expect(Reflect.get(globalThis, marker)).toBeUndefined()
      await rm(dir, { recursive: true, force: true })
    }
  })

  it('cascades provider removal to an injected consumer and reactivates both', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'gerclaw-evidence-hotplug-'))
    const config = join(dir, 'cordis.yml')
    const consumer = join(dir, 'consumer.mjs')
    const failing = join(dir, 'failing.mjs')
    await writeFile(consumer, [
      'export const inject = ["gerclawMedicalEvidence"]',
      'export function apply(ctx) {',
      '  ctx.effect(() => {',
      '    globalThis[Symbol.for("gerclaw.test.evidence-consumer")] = true',
      '    return () => { delete globalThis[Symbol.for("gerclaw.test.evidence-consumer")] }',
      '  }, "gerclaw.test.evidence-consumer")',
      '}',
      '',
    ].join('\n'))
    await writeFile(failing, 'export function apply() { throw new Error("candidate apply failed") }\n')
    await writeFile(config, [
      '- id: evidence-provider',
      `  name: "${evidenceProvider}"`,
      '- id: evidence-consumer',
      `  name: "${pathToFileURL(consumer).href}"`,
      '',
    ].join('\n'))
    const ctx = await boot('gerclaw-evidence-hotplug-test', config)
    const marker = Symbol.for('gerclaw.test.evidence-consumer')
    try {
      const provider = entryById(ctx, 'evidence-provider')
      const consumerEntry = entryById(ctx, 'evidence-consumer')
      const firstProviderFiber = provider.fiber
      const firstConsumerFiber = consumerEntry.fiber
      expect(firstProviderFiber?.state).toBe(FiberState.ACTIVE)
      expect(firstConsumerFiber?.state).toBe(FiberState.ACTIVE)
      expect(Reflect.get(globalThis, marker)).toBe(true)
      expect(ctx.get('gerclawMedicalEvidence')).toBeDefined()

      await ctx.loader.update(provider.id, { disabled: true })
      await ctx.loader.await()
      expect(provider.fiber).toBeUndefined()
      expect(consumerEntry.fiber?.state).toBe(FiberState.PENDING)
      expect(Reflect.get(globalThis, marker)).toBeUndefined()
      expect(ctx.get('gerclawMedicalEvidence')).toBeUndefined()

      await ctx.loader.update(provider.id, { disabled: false })
      await ctx.loader.await()
      expect(provider.fiber?.state).toBe(FiberState.ACTIVE)
      expect(consumerEntry.fiber?.state).toBe(FiberState.ACTIVE)
      expect(provider.fiber).not.toBe(firstProviderFiber)
      expect(Reflect.get(globalThis, marker)).toBe(true)
      expect(ctx.get('gerclawMedicalEvidence')).toBeDefined()

      const successfulProviderFiber = provider.fiber
      await expect(provider.update({ name: pathToFileURL(failing).href })).rejects.toThrow('candidate apply failed')
      expect(provider.options.name).toBe(evidenceProvider)
      expect(provider.fiber).not.toBe(successfulProviderFiber)
      expect(provider.fiber?.state).toBe(FiberState.ACTIVE)
      expect(consumerEntry.fiber?.state).toBe(FiberState.ACTIVE)
      expect(Reflect.get(globalThis, marker)).toBe(true)
      expect(ctx.get('gerclawMedicalEvidence')).toBeDefined()
    } finally {
      await ctx.fiber.dispose()
      expect(Reflect.get(globalThis, marker)).toBeUndefined()
      await rm(dir, { recursive: true, force: true })
    }
  })
})
