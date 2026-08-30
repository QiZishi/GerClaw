import { mkdtemp, mkdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { FiberState } from '@deepseek-ai/cordis'
import { boot } from '@deepseek-ai/dsh-app-boot'
import { afterEach, describe, expect, it, vi } from 'vitest'

const roots: string[] = []

afterEach(async () => {
  const { rm } = await import('node:fs/promises')
  await Promise.all(roots.splice(0).map(path => rm(path, { recursive: true, force: true })))
})

const quote = (value: string) => JSON.stringify(value)
const repoRoot = join(import.meta.dirname, '../../../..')
const pluginUrl = (relativePath: string) => pathToFileURL(join(repoRoot, relativePath, 'lib/index.js')).href

describe('GerClaw RAG real Loader lifecycle invariant', () => {
  it('waits for a missing provider, cascades on disable, restores, and rolls back an invalid update', async () => {
    const runtimeRoot = join(repoRoot, '.gerclaw', 'test-loader')
    await mkdir(runtimeRoot, { recursive: true })
    const root = await mkdtemp(join(runtimeRoot, 'rag-'))
    roots.push(root)
    const knowledge = join(root, 'knowledge')
    await mkdir(knowledge)
    await writeFile(join(knowledge, 'sleep.md'), '# 睡眠管理\n老年人应保持规律作息并记录睡眠变化。')
    const configPath = join(root, 'cordis.yml')
    await writeFile(configPath, [
      '- id: subprocess',
      `  name: ${quote(pluginUrl('packages/subprocess/subprocess-local'))}`,
      '- id: private-storage',
      `  name: ${quote(pluginUrl('packages/storage/storage'))}`,
      '- id: private-sqlite',
      `  name: ${quote(pluginUrl('packages/storage/storage-sqlite'))}`,
      `  config: { path: ${quote(join(root, 'private.sqlite'))} }`,
      '- id: private-domain',
      `  name: ${quote(pluginUrl('packages/storage/storage-domain'))}`,
      '  config: { backend: sqlite }',
      '- id: private-library-runtime',
      `  name: ${quote(pluginUrl('packages/gerclaw/library-dsh-runtime'))}`,
      '  config: { embeddingDimensions: 32 }',
      '- id: private-library',
      `  name: ${quote(pluginUrl('packages/gerclaw/library-dsh'))}`,
      '  config: { library: gerclaw-test-private }',
      '- id: shared-group',
      '  name: cordis:group',
      '  group: true',
      '  isolate:',
      '    storage: true',
      '    storage.backend.sqlite: true',
      '    storageDomain: true',
      '    gerclawLibraryRuntime: true',
      '  config:',
      '    - id: shared-storage',
      `      name: ${quote(pluginUrl('packages/storage/storage'))}`,
      '    - id: shared-sqlite',
      `      name: ${quote(pluginUrl('packages/storage/storage-sqlite'))}`,
      `      config: { path: ${quote(join(root, 'shared.sqlite'))} }`,
      '    - id: shared-domain',
      `      name: ${quote(pluginUrl('packages/gerclaw/storage-domain-isolated'))}`,
      '      config: { backend: sqlite }',
      '    - id: shared-library-runtime',
      `      name: ${quote(pluginUrl('packages/gerclaw/library-dsh-runtime'))}`,
      '      config: { embeddingDimensions: 32 }',
      '    - id: shared-knowledge',
      `      name: ${quote(pluginUrl('packages/gerclaw/local-rag'))}`,
      '      config:',
      `        knowledgeBasePath: ${quote(knowledge)}`,
      `        sharedIndexRoot: ${quote(join(root, 'index-meta'))}`,
      '        embeddingDimensions: 32',
      '        rerankApiKey: test-key',
      '        rerankUrl: http://127.0.0.1:1',
      '        rerankModel: test-rerank',
      '- id: rag',
      `  name: ${quote(pluginUrl('packages/gerclaw/rag'))}`,
    ].join('\n'))

    const ctx = await boot('gerclaw-rag-loader-test', configPath)
    try {
      await ctx.loader.await()
      const entries = () => [...ctx.loader.entries()]
      const byId = (id: string) => {
        const entry = entries().find(candidate => candidate.options.id === id)
        if (!entry) throw new Error(`missing Loader entry ${id}`)
        return entry
      }
      await vi.waitFor(() => {
        expect(ctx.gerclawSharedKnowledge.status().state).toBe('ready')
      }, { timeout: 10_000 })
      const rag = byId('rag')
      const firstFiber = rag.fiber
      const firstService = ctx.get('gerclawRag')
      expect(firstFiber?.state).toBe(FiberState.ACTIVE)
      expect(firstService).toBeDefined()

      const runtime = byId('private-library-runtime')
      const library = byId('private-library')
      await runtime.update({ disabled: true })
      await vi.waitFor(() => {
        expect(library.fiber?.state).toBe(FiberState.PENDING)
        expect(rag.fiber?.state).toBe(FiberState.PENDING)
        expect(ctx.get('gerclawRag')).toBeUndefined()
      })

      await runtime.update({ disabled: false })
      await vi.waitFor(() => {
        expect(rag.fiber?.state).toBe(FiberState.ACTIVE)
        expect(ctx.get('gerclawRag')).toBeDefined()
      })
      // Loader owns one stable entry fiber. Cordis unloads and recreates the
      // service implementation inside it when a required provider returns.
      expect(rag.fiber).toBe(firstFiber)
      expect(ctx.get('gerclawRag')).not.toBe(firstService)

      const restoredFiber = rag.fiber
      await expect(rag.update({
        name: pathToFileURL(join(root, 'missing-rag-provider.js')).href,
      })).rejects.toThrow(/failed to import loader entry rag/u)
      expect(rag.fiber).toBe(restoredFiber)
      expect(rag.fiber?.state).toBe(FiberState.ACTIVE)
      expect(ctx.get('gerclawRag')).toBeDefined()
    } finally {
      await ctx.fiber.dispose()
    }
  })
})
