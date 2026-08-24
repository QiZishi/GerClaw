import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { calculateTrends } from '../../chronic-care/src/index.ts'
import { detectCompanionSignal } from '../../companion/src/index.ts'
import { normalizeHealthProfile } from '../../health-profile/src/index.ts'
import {
  advancePrescriptionIntake,
  evidenceFromLocalHits,
  prescriptionRequestFromIntake,
} from '../../prescription/src/index.ts'
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
    expect(evidenceFromLocalHits([{ chunkId: 'chunk-1', documentId: 'md/source.md', seq: 3, snippet: '原文', score: 0.9, origin: 'knowledge-base' }])[0]).toMatchObject({ locator: 'md/source.md:3', snippet: '原文' })
  })

  it('prescription collects required fields through at most five chat turns', () => {
    const first = advancePrescriptionIntake(undefined, {}, '2026-01-01T00:00:00.000Z')
    expect(first).toMatchObject({
      status: 'collecting',
      conversationTurns: 1,
      missingFields: ['healthGoal', 'currentConcerns'],
      nextQuestion: '这次您最希望改善或管理的健康目标是什么？',
    })
    const second = advancePrescriptionIntake(first, {
      healthGoal: '改善睡眠',
      documentRefs: ['doc-1'],
    })
    expect(second).toMatchObject({
      status: 'collecting',
      conversationTurns: 2,
      healthGoal: '改善睡眠',
      missingFields: ['currentConcerns'],
    })
    const complete = advancePrescriptionIntake(second, {
      currentConcerns: '夜间易醒',
      currentMedications: '阿司匹林每日一次',
    })
    expect(prescriptionRequestFromIntake(complete)).toMatchObject({
      healthGoals: ['改善睡眠'],
      currentConcerns: ['夜间易醒'],
      currentMedications: '阿司匹林每日一次',
      documentRefs: ['doc-1'],
    })
  })

  it('prescription refuses generation when required facts are still absent after turn five', () => {
    let intake = advancePrescriptionIntake(undefined, {})
    for (let turn = 2; turn <= 5; turn += 1)
      intake = advancePrescriptionIntake(intake, {})
    expect(intake).toMatchObject({
      status: 'limit_reached',
      conversationTurns: 5,
      missingFields: ['healthGoal', 'currentConcerns'],
    })
    expect(() => prescriptionRequestFromIntake(intake)).toThrow('尚未收集完整')
  })

  it('prescription intake never overwrites confirmed facts and asks only one question', () => {
    const first = advancePrescriptionIntake(undefined, {
      healthGoal: '改善步行耐力',
      documentRefs: ['report-a', 'report-a'],
    })
    const second = advancePrescriptionIntake(first, {
      healthGoal: '不应覆盖',
      currentConcerns: '步行十分钟后气促',
      documentRefs: ['report-b'],
    })
    expect(first.nextQuestion).toBe('目前最困扰您的症状、问题或检查异常是什么？')
    expect(first.nextQuestion?.match(/[？?]/g)).toHaveLength(1)
    expect(second).toMatchObject({
      status: 'information_complete',
      healthGoal: '改善步行耐力',
      currentConcerns: '步行十分钟后气促',
      documentRefs: ['report-a', 'report-b'],
    })
  })
})

describe('GerClaw integration plugin contracts', () => {
  it('system-prompt replaces the developer persona and keeps Plan/Goal', () => {
    expect(GERCLAW_SYSTEM_PROMPT).toContain('GerClaw 智能健康助手')
    expect(GERCLAW_SYSTEM_PROMPT).toContain('plan 模式')
    expect(GERCLAW_SYSTEM_PROMPT).toContain('goal 模式')
    expect(GERCLAW_SYSTEM_PROMPT).not.toContain('插件开发')
    expect(GERCLAW_SYSTEM_PROMPT).toContain('普通健康咨询、症状描述、用药陈述或语音转写不得被推断为五大处方请求')
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
    const [definition, provider, consumer] = await Promise.all([
      source('speech/src/index.ts'),
      source('speech-qianwen/src/index.ts'),
      source('voice/src/service.ts'),
    ])
    const profile = await source('profile-bundle/cordis.patch.yml')
    expect(definition).toContain('qwen3-asr-flash-realtime')
    expect(definition).toContain('qwen3-tts-instruct-flash-realtime')
    expect(consumer).toContain('/gerclaw/api/voice/asr-stream')
    expect(provider).toContain('extends SpeechProvider')
    expect(consumer).toContain("static inject = ['speech'")
    expect(consumer).toContain("path: '/gerclaw/api/voice/tts'")
    expect(await source('client/src/index.ts')).not.toContain("'talk',")
    for (const text of [definition, provider, consumer]) {
      expect(text).not.toContain('SILICONFLOW_')
      expect(text).not.toContain('MIMO_')
    }
    expect(profile).not.toContain('fallbackToBrowser')
    expect(profile).not.toMatch(/engine:\s*(?:auto|browser|edge-tts|piper|whisper|funasr)/)
  })

  it('RAG composes isolated shared and account-private dsh-library providers without Tool-as-API', async () => {
    const shared = await source('local-rag/src/index.ts')
    const privateProvider = await source('library-dsh/src/index.ts')
    const rag = await source('rag/src/index.ts')
    const isolatedDomain = await source('storage-domain-isolated/src/index.ts')
    const profile = await source('profile-bundle/cordis.patch.yml')
    expect(profile).toContain('name: "@gerclaw/library-dsh"')
    expect(profile).toContain('name: "@gerclaw/shared-knowledge"')
    expect(profile).toContain('name: "@gerclaw/rag"')
    expect(profile).toContain('name: "@gerclaw/storage-domain-isolated"')
    expect(profile).toContain('name: "@deepseek-ai/dsh-storage-sqlite"')
    expect(profile).toContain('storage.backend.sqlite: gerclaw-shared-rag')
    expect(privateProvider).toContain('extends GerclawLibrary')
    expect(privateProvider).toContain('this.ctx.storageDomain.open(libraryDomainSpec)')
    expect(shared).toContain('extends GerclawSharedKnowledge')
    expect(shared).toContain('createCorpusManifest')
    expect(shared).toContain('await rename(staging, versionDir)')
    expect(rag).toContain("static inject = ['gerclawLibrary', 'gerclawSharedKnowledge']")
    expect(rag).toContain('/rerank')
    expect(isolatedDomain).toContain("ctx.inject(['storage', ...backendServices]")
    expect(isolatedDomain).toContain('new DomainFacility(domainCtx, config)')
    for (const text of [privateProvider, shared, rag]) {
      expect(text).not.toContain('new SqliteStorageBackend(')
      expect(text).not.toContain('DomainFacility(')
      expect(text).not.toContain('ctx.tools.execute(')
    }
    expect(profile).toContain("GERCLAW_ROOT_DIR, 'knowledge-base'")
    expect(profile).toContain("'.gerclaw', 'shared-rag'")
  })

  it('medical-evidence keeps only the three public providers', async () => {
    const text = await source('medical-evidence/src/index.ts')
    expect(text).toContain('eutils.ncbi.nlm.nih.gov')
    expect(text).toContain('api.fda.gov')
    expect(text).toContain('wsearch.nlm.nih.gov')
    expect(text).not.toContain('persona')
  })

  it('tenant-gateway isolates child Hosts and uses strict cookies', async () => {
    const gateway = await source('tenant-gateway/src/index.ts')
    const host = await source('tenant-host-local/src/index.ts')
    expect(gateway).toContain('SameSite=Strict')
    expect(gateway).toContain("static inject = ['webServer', 'gerclawAuth', 'gerclawTenantHost', 'multiTenant']")
    expect(gateway).not.toContain('DSH_HOME')
    expect(host).toContain('DSH_HOME: dshHome')
    expect(host).toContain('GERCLAW_ACCOUNT_DATA_DIR')
    expect(host).toContain("'plugin',")
    expect(host).toContain("join(this.config.dataDir, 'guests')")
    expect(host).not.toContain('child_process')
  })

  it('profile-bundle loads native Plan/Goal and every GerClaw provider through Cordis', async () => {
    const text = await source('profile-bundle/cordis.patch.yml')
    const agent = await source('profile-bundle/presets/gerclaw/agent.cordis.yml')
    for (const name of ['goal', '@gerclaw/system-prompt', '@gerclaw/voice', '@gerclaw/shared-knowledge', '@gerclaw/rag', '@gerclaw/app'])
      expect(text).toContain(name)
    expect(agent).toContain('plan-mode')
    expect(await source('profile-bundle/package.json')).toContain('dsh-mineru')
    expect(await source('local-rag/package.json')).toContain('dsh-library')
  })

  it('app is GerClaw-only, chat-centred, and exposes seven exports', async () => {
    const client = await source('client-ui/src/client/index.ts')
    const navigation = await source('client-ui/src/client/MedicalNavigation.tsx')
    const app = await source('client/src/index.ts')
    expect(client).toContain('老年慢病智慧诊疗助手')
    expect(navigation).toContain('健康对话')
    expect(navigation).toContain('startPrescription')
    expect(navigation).not.toContain('<PrescriptionForm')
    expect(navigation).not.toContain("id: 'voice'")
    expect(client).not.toContain('DeepSeek Harness')
    expect(app).toContain("nativeSession.append('turn/start'")
    expect(app).toContain("nativeSession.append('turn/end'")
    for (const format of ['md', 'html', 'docx', 'pdf', 'png', 'jpg', 'json'])
      expect(app).toContain(`'${format}'`)
    expect(app).toContain('workspaceRef = `artifacts/${artifactId}.${format}`')
    expect(app).toContain("createHash('sha256')")
  })

  it('submits, cancels, restores and exports medical work through typed DSH Remote', async () => {
    const app = await source('client/src/index.ts')
    const appPackage = await source('client/package.json')
    const profile = await source('profile-bundle/cordis.patch.yml')
    const client = await source('client-ui/src/client/index.ts')
    const feature = await source('client-ui/src/client/MedicalFeature.tsx')
    for (const path of ['./types', './typert', './remote', './package.json'])
      expect(appPackage).toContain(`"${path}"`)
    for (const method of ['submit', 'cancel', 'status', 'export'])
      expect(app).toContain(`@Remote('${method}')`)
    expect(profile).toContain('- "@gerclaw/voice"')
    expect(profile).toContain('- "@gerclaw/app"')
    expect(client).toContain("from '@gerclaw/app/remote'")
    expect(client).toContain('ctx.remote.$mount(gerclawAppRemote)')
    expect(client).toContain('ctx.remote.gerclawApp.submit')
    expect(feature).not.toMatch(/fetch\(['"]\/gerclaw\/api\/(?:cga|medication|profile|chronic|companion|evidence)/u)
  })

  it('protects the native chat prescription flow, brand layout and sidebar order', async () => {
    const client = await source('client-ui/src/client/index.ts')
    const navigation = await source('client-ui/src/client/MedicalNavigation.tsx')
    const brand = await source('client-ui/src/client/Brand.tsx')
    const css = await source('client-ui/src/client/product.css')
    const app = await source('client/src/index.ts')
    expect(client).toContain("conversation.send('我想开始一份新的五大处方")
    expect(app).toContain("throw new Error('只有用户明确要求开始五大处方时才能启动资料收集')")
    expect(app).toContain('this.ctx.gerclawRag.search(query, 8, signal)')
    expect(navigation).not.toMatch(/PrescriptionForm|处方表单/)
    expect(brand).toContain('<strong>GerClaw</strong>')
    expect(brand).toContain('<span>老年慢病智慧诊疗助手</span>')
    expect(brand).toContain('src="/brand-icon.png"')
    expect(css).toContain('[data-gerclaw-new-conversation]')
    expect(css).toContain('order: 1')
    expect(css).toContain('[data-gerclaw-nav-actions]')
    expect(css).toContain('order: 2')
    expect(css).toContain('[data-gerclaw-conversation-history]')
    expect(css).toContain('order: 3')
    expect(css).toContain('[data-gerclaw-sidebar-settings]')
    expect(css).toContain('order: 4')
    expect(css).toContain('button:has([data-gerclaw-brand-name])')
    expect(css).toContain('overflow: visible !important')
  })

  it('protects the product-focused login copy', async () => {
    const login = await source('tenant-gateway/public/login.html')
    expect(login).toContain('面向老年慢病诊疗与健康管理，从资料理解、综合评估到个体化建议，全程在自然对话中完成。')
    expect(login).toContain('对话收集资料，生成药物、运动、营养、心理和康复处方')
    expect(login).toContain('完成五类老年综合评估，联动用药核对与风险提醒')
    expect(login).toContain('支持语音与病历资料解析，结合本地医学知识库提供可追溯依据')
    expect(login).not.toContain('医生与患者使用相同完整功能')
    expect(login).not.toContain('每个账号的数据单独保存')
  })

  it('keeps GerClaw persisted events readable after a Host restart', async () => {
    const knownEvents = await readFile(
      join(root, '../core/session/src/known-event-types.ts'),
      'utf8',
    )
    expect(knownEvents).toContain("'gerclaw/task'")
    expect(knownEvents).toContain("'gerclaw/prescription-intake'")
    expect(knownEvents).toContain("'gerclaw/voice'")
  })

  it('launcher reads the root env and starts the real profile patch', async () => {
    const text = await source('launcher/src/bin.ts')
    expect(text).toContain("join(root, '.env')")
    expect(text).toContain("'plugin', '--profile', 'web'")
    expect(text).toContain('gatewayPackage')
    expect(text).not.toContain("'--patch'")
    expect(text).toContain('--profile')
  })
})
