import { createHash } from 'node:crypto'
import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { createCorpusManifest, planSharedShards } from '../src/index.ts'

describe('shared medical corpus manifest', () => {
  it('covers all 437 copied sources with stable path and SHA-256 identity', async () => {
    const root = join(import.meta.dirname, '../../../..', 'knowledge-base')
    const sourceRoot = '/Users/qizs/conclusion/gerclaw/gerclaw-main-codex/knowledge-base'
    const [target, source] = await Promise.all([
      createCorpusManifest(root),
      createCorpusManifest(sourceRoot),
    ])
    expect(target.files).toHaveLength(437)
    expect(target.files).toEqual(source.files)
    expect(target.version).toBe(source.version)
    expect(target).toMatchObject({
      schemaVersion: 3,
      index: {
        chunkSize: 4_000,
        chunkOverlap: 400,
        embeddingDimensions: 1_024,
        shardMaxChunks: 80,
        segmentChars: 180_000,
        segmentOverlap: 4_000,
      },
    })
  })

  it('changes the version when a path or byte changes', async () => {
    const root = await mkdtemp(join(tmpdir(), 'gerclaw-rag-manifest-'))
    await mkdir(join(root, 'a'))
    await writeFile(join(root, 'a', 'one.md'), '原文')
    const first = await createCorpusManifest(root)
    await writeFile(join(root, 'a', 'one.md'), '修改')
    const second = await createCorpusManifest(root)
    expect(first.version).not.toBe(second.version)
    expect(second.files[0]?.sha256).toBe(createHash('sha256').update(await readFile(join(root, 'a', 'one.md'))).digest('hex'))
  })

  it('changes the version when the embedding identity changes', async () => {
    const root = await mkdtemp(join(tmpdir(), 'gerclaw-rag-config-'))
    await writeFile(join(root, 'one.md'), '同一份原文')
    const first = await createCorpusManifest(root, { embeddingModel: 'model-a' })
    const second = await createCorpusManifest(root, { embeddingModel: 'model-b' })
    expect(first.files).toEqual(second.files)
    expect(first.version).not.toBe(second.version)
  })

  it('partitions large sources into bounded dsh-library shards without losing source identity', () => {
    const shards = planSharedShards([
      { path: 'md/睡眠障碍md/guide-a.md', content: '睡眠管理。'.repeat(40_000) },
      { path: 'md/睡眠障碍md/guide-b.md', content: '老年睡眠。'.repeat(4_000) },
      { path: 'md/冠心病md/guide-c.md', content: '冠心病管理。'.repeat(2_000) },
    ])
    expect(shards.length).toBeGreaterThan(1)
    expect(shards.every(shard => shard.estimatedChunks <= 80)).toBe(true)
    expect(new Set(shards.flatMap(shard => shard.segments.map(segment => segment.path)))).toEqual(new Set([
      'md/睡眠障碍md/guide-a.md',
      'md/睡眠障碍md/guide-b.md',
      'md/冠心病md/guide-c.md',
    ]))
    expect(shards.flatMap(shard => shard.segments).some(segment => segment.seqBase > 0)).toBe(true)
  })
})
