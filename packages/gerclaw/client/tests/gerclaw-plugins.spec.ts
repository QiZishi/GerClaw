import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { calculateTrends } from '../../chronic-care/src/index.ts'
import { detectCompanionSignal } from '../../companion/src/index.ts'
import { normalizeHealthProfile } from '../../health-profile/src/index.ts'
import { evidenceFromLocalHits } from '../../prescription/src/index.ts'
import { deriveRiskAlerts } from '../../risk-alert/src/index.ts'
import { GERCLAW_SYSTEM_PROMPT } from '../../system-prompt/src/index.ts'

const root = join(import.meta.dirname, '../..')
const source = (path: string) => readFile(join(root, path), 'utf8')

describe('GerClaw domain plugins', () => {
  it('chronic-care calculates deterministic trends', () => {
    expect(calculateTrends([
      { measurementId: '1', conditionId: 'bp', metricLabel: '收缩压', value: 145, unit: 'mmHg', measuredAt: '2026-01-01', createdAt: '2026-01-01' },
      { measurementId: '2', conditionId: 'bp', metricLabel: '收缩压', value: 135, unit: 'mmHg', measuredAt: '2026-01-02', createdAt: '2026-01-02' },
    ])[0]?.direction).toBe('down')
  })

  it('companion and risk-alert preserve urgent signals', () => {
    expect(detectCompanionSignal('我想伤害自己').urgent).toBe(true)
    expect(deriveRiskAlerts({ companion: { urgent: true } })[0]).toMatchObject({ severity: 'critical', source: 'chat' })
  })

  it('health-profile normalizes owner-authoritative fields', () => {
    const profile = normalizeHealthProfile({ profileId: 'p1', age: 75, allergies: ['青霉素', '青霉素'], conditions: [], medications: [], goals: [], preferences: [] })
    expect(profile).toMatchObject({ profileId: 'p1', age: 75, allergies: ['青霉素'], revision: 1 })
  })

  it('prescription maps local RAG citations without changing source identity', () => {
    expect(evidenceFromLocalHits([{ chunkId: 'chunk-1', documentId: 'md/source.md', seq: 3, snippet: '原文', score: 0.9 }])[0]).toMatchObject({ locator: 'md/source.md:3', snippet: '原文' })
  })
})

describe('GerClaw integration plugin contracts', () => {
  it('system-prompt replaces the developer persona and keeps Plan/Goal', () => {
    expect(GERCLAW_SYSTEM_PROMPT).toContain('GerClaw 智能健康助手')
    expect(GERCLAW_SYSTEM_PROMPT).toContain('plan 模式')
    expect(GERCLAW_SYSTEM_PROMPT).toContain('goal 模式')
    expect(GERCLAW_SYSTEM_PROMPT).not.toContain('插件开发')
  })

  it('skills exposes exactly the four GerClaw user skills', async () => {
    const packageText = await source('skills/package.json')
    const skillTexts = await Promise.all([
      'followup-questionnaire',
      'risk-assessment',
      'health-education',
      'medication-reminder',
    ].map(name => source(`skills/skills/${name}/SKILL.md`)))
    const skillPackage = JSON.parse(packageText) as { name?: unknown }
    expect(skillPackage.name).toBe('@gerclaw/skills')
    expect(skillTexts.every(text => text.includes('name:') && text.includes('description:'))).toBe(true)
  })

  it('voice is Qianwen-only and never routes through SiliconFlow', async () => {
    const text = await source('voice/src/index.ts')
    expect(text).toContain('qwen3-asr-flash-realtime')
    expect(text).toContain('qwen3-tts-instruct-flash-realtime')
    expect(text).toContain('/gerclaw/api/voice/asr-stream')
    expect(text).not.toContain('SILICONFLOW_')
    expect(text).not.toContain('MIMO_')
  })

  it('local-rag uses dsh-library with account-local documents and SiliconFlow rerank', async () => {
    const text = await source('local-rag/src/index.ts')
    expect(text).toContain("from 'dsh-library'")
    expect(text).toContain("'gerclaw-user'")
    expect(text).toContain('/rerank')
    expect(text).not.toContain('embedHash')
  })

  it('medical-evidence keeps only the three public providers', async () => {
    const text = await source('medical-evidence/src/index.ts')
    expect(text).toContain('eutils.ncbi.nlm.nih.gov')
    expect(text).toContain('api.fda.gov')
    expect(text).toContain('wsearch.nlm.nih.gov')
    expect(text).not.toContain('persona')
  })

  it('tenant-gateway isolates child Hosts and uses strict cookies', async () => {
    const text = await source('tenant-gateway/src/index.ts')
    expect(text).toContain('DSH_HOME')
    expect(text).toContain('SameSite=Strict')
    expect(text).toContain('GERCLAW_ACCOUNT_DATA_DIR')
  })

  it('profile-bundle loads native Plan/Goal and every GerClaw provider through Cordis', async () => {
    const text = await source('profile-bundle/cordis.patch.yml')
    for (const name of ['plan-mode', 'goal', '@gerclaw/system-prompt', '@gerclaw/voice', '@gerclaw/local-rag', '@gerclaw/app'])
      expect(text).toContain(name)
    expect(text).toContain('dsh-mineru')
    expect(await source('local-rag/package.json')).toContain('dsh-library')
  })

  it('app is GerClaw-only, chat-centred, and exposes seven exports', async () => {
    const html = await source('client/public/index.html')
    expect(html).toContain('icon.png')
    expect(html).toContain('健康对话')
    expect(html).not.toContain('>语音<')
    expect(html).not.toContain('DeepSeek Harness')
    for (const format of ['md', 'html', 'docx', 'pdf', 'png', 'jpg', 'json'])
      expect(html).toContain(`'${format}'`)
  })

  it('launcher reads the root env and starts the real profile patch', async () => {
    const text = await source('launcher/src/bin.ts')
    expect(text).toContain("join(root, '.env')")
    expect(text).toContain('gateway.patch.yml')
    expect(text).toContain('--profile')
  })
})
