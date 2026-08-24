import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { describe, expect, it } from 'vitest'
import type { Context } from '@deepseek-ai/cordis'
import { boot } from '@deepseek-ai/dsh-app-boot'
import type {} from '@gerclaw/companion'

const companionPlugin = pathToFileURL(fileURLToPath(
  new URL('../../companion/lib/index.js', import.meta.url),
)).href

const entryById = (ctx: Context, id: string) => {
  const entry = [...ctx.loader.entries()].find(candidate => candidate.options.id === id)
  if (entry === undefined) throw new Error(`真实 Loader 树缺少 ${id}`)
  return entry
}

describe('GerClaw native DSH Loader hot-plug', () => {
  it('unloads and reloads a real GerClaw provider through Loader.update', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'gerclaw-hotplug-'))
    const config = join(dir, 'cordis.yml')
    await writeFile(config, [
      '- id: gerclaw-companion',
      `  name: "${companionPlugin}"`,
      '',
    ].join('\n'))
    const ctx = await boot('gerclaw-hotplug-test', config)
    try {
      const entry = entryById(ctx, 'gerclaw-companion')
      const firstFiber = entry.fiber
      expect(firstFiber).toBeDefined()
      expect(ctx.gerclawCompanion.detect('今天心情平静')).toMatchObject({ urgent: false })

      await ctx.loader.update(entry.id, { disabled: true })
      await ctx.loader.await()
      expect(entry.fiber).toBeUndefined()
      expect(Reflect.get(ctx, 'gerclawCompanion')).toBeUndefined()

      await ctx.loader.update(entry.id, { disabled: false })
      await ctx.loader.await()
      expect(entry.fiber).toBeDefined()
      expect(entry.fiber).not.toBe(firstFiber)
      expect(ctx.gerclawCompanion.detect('今天心情平静')).toMatchObject({ urgent: false })
    } finally {
      await ctx.fiber.dispose()
      await rm(dir, { recursive: true, force: true })
    }
  })
})
