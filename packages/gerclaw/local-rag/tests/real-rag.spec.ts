import { mkdtemp, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { FiberState, type Context } from '@deepseek-ai/cordis'
import { boot } from '@deepseek-ai/dsh-app-boot'
import type {} from '@gerclaw/library'
import { afterAll, describe, expect, it } from 'vitest'

const ENABLED = process.env.GERCLAW_REAL_RAG === '1'
const repoRoot = join(import.meta.dirname, '../../../..')
const roots: string[] = []

const quote = (value: string): string => JSON.stringify(value)
const pluginUrl = (relativePath: string): string => pathToFileURL(
  join(repoRoot, relativePath, 'lib/index.js'),
).href

const createConfig = async (root: string): Promise<string> => {
  const configPath = join(root, 'cordis.yml')
  const embeddingCommand = [
    process.execPath,
    `--env-file=${join(repoRoot, '.env')}`,
    join(repoRoot, 'packages/gerclaw/local-rag/scripts/siliconflow-embedder.mjs'),
  ].join(' ')
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
    '  config:',
    `    embeddingCommand: ${quote(embeddingCommand)}`,
    '    embeddingDimensions: 1024',
    '- id: private-library',
    `  name: ${quote(pluginUrl('packages/gerclaw/library-dsh'))}`,
    '  config:',
    '    library: gerclaw-real-rag-private',
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
    `      config: { path: ${quote(join(repoRoot, '.gerclaw/shared-rag/index.sqlite'))} }`,
    '    - id: shared-domain',
    `      name: ${quote(pluginUrl('packages/gerclaw/storage-domain-isolated'))}`,
    '      config: { backend: sqlite }',
    '    - id: shared-library-runtime',
    `      name: ${quote(pluginUrl('packages/gerclaw/library-dsh-runtime'))}`,
    '      config:',
    `        embeddingCommand: ${quote(embeddingCommand)}`,
    '        embeddingDimensions: 1024',
    '    - id: shared-knowledge',
    `      name: ${quote(pluginUrl('packages/gerclaw/local-rag'))}`,
    '      config:',
    `        knowledgeBasePath: ${quote(join(repoRoot, 'knowledge-base'))}`,
    `        sharedIndexRoot: ${quote(join(repoRoot, '.gerclaw/shared-rag'))}`,
    '        library: gerclaw-medical-sf-v3',
    '        embeddingDimensions: 1024',
    "        embeddingModel: !!js process.env.EMBEDDING_MODEL || 'BAAI/bge-m3'",
    '        rerankApiKey: !!js process.env.SILICONFLOW_API_KEY',
    '        rerankUrl: !!js process.env.SILICONFLOW_URL',
    '        rerankModel: !!js process.env.RERANK_MODEL',
    '- id: rag',
    `  name: ${quote(pluginUrl('packages/gerclaw/rag'))}`,
  ].join('\n'))
  return configPath
}

const bootAccount = async (label: string): Promise<Context> => {
  const root = await mkdtemp(join(tmpdir(), `gerclaw-real-rag-${label}-`))
  roots.push(root)
  await mkdir(root, { recursive: true })
  return boot(`gerclaw-real-rag-${label}`, await createConfig(root))
}

afterAll(async () => {
  const { rm } = await import('node:fs/promises')
  await Promise.all(roots.splice(0).map(root => rm(root, { recursive: true, force: true })))
})

describe.skipIf(!ENABLED)('GerClaw real shared/private RAG composition', () => {
  it('retrieves the READY corpus, isolates private documents, and hot-plugs the provider', async () => {
    const first = await bootAccount('first')
    const second = await bootAccount('second')
    try {
      await Promise.all([first.loader.await(), second.loader.await()])
      await expect.poll(() => first.gerclawSharedKnowledge.status(), {
        timeout: 30_000,
      }).toMatchObject({
        state: 'ready',
        total: 437,
        indexed: 437,
      })
      const shared = await first.gerclawRag.search('老年高血压患者睡眠管理建议', 5)
      expect(shared).toHaveLength(5)
      expect(shared.every(hit => hit.origin === 'knowledge-base')).toBe(true)
      expect(shared.some(hit => hit.documentId.includes('睡眠'))).toBe(true)

      const marker = 'GC_REAL_PRIVATE_RAG_82719'
      await first.gerclawLibrary.add('真实私有随访记录', `${marker}，晨起血压为138/82毫米汞柱。`)
      const firstHits = await first.gerclawRag.search(marker, 8)
      expect(firstHits.some(hit => hit.origin === 'user' && hit.snippet.includes(marker))).toBe(true)
      const secondHits = await second.gerclawRag.search(marker, 8)
      expect(secondHits.some(hit => hit.origin === 'user' || hit.snippet.includes(marker))).toBe(false)

      const entries = [...first.loader.entries()]
      const library = entries.find(entry => entry.options.id === 'private-library')
      const rag = entries.find(entry => entry.options.id === 'rag')
      if (!library || !rag) throw new Error('真实 Loader 树缺少 RAG 组合项')
      const firstService = first.get('gerclawRag')
      await library.update({ disabled: true })
      await expect.poll(() => rag.fiber?.state).toBe(FiberState.PENDING)
      expect(first.get('gerclawRag')).toBeUndefined()
      await library.update({ disabled: false })
      await expect.poll(() => rag.fiber?.state).toBe(FiberState.ACTIVE)
      expect(first.get('gerclawRag')).toBeDefined()
      expect(first.get('gerclawRag')).not.toBe(firstService)
    } finally {
      await Promise.all([first.fiber.dispose(), second.fiber.dispose()])
    }
  }, 180_000)
})
