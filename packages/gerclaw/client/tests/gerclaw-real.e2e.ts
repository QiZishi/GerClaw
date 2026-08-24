import { randomBytes } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import type { Browser, BrowserContext, Locator, Page } from 'playwright'
import { chromium } from 'playwright'
import { afterAll, beforeAll, describe, expect, it, onTestFailed } from 'vitest'

const BASE_URL = process.env.GERCLAW_E2E_BASE_URL ?? 'http://127.0.0.1:3000'
const AUDIO_FIXTURE = fileURLToPath(new URL('./fixtures/gerclaw-health.wav', import.meta.url))
const DOCUMENT_FIXTURE = fileURLToPath(new URL('./fixtures/health-note.txt', import.meta.url))
const ENABLED = process.env.GERCLAW_REAL_E2E === '1'

type Identity = {
  label: '医生' | '患者'
  username: string
  password: string
}

const required = (name: string): string => {
  const value = process.env[name]
  if (!value) throw new Error(`真实 GerClaw E2E 缺少环境变量：${name}`)
  return value
}

const identities = (): Identity[] => [
  {
    label: '医生',
    username: 'gc_doctor_test_20260823',
    password: required('GERCLAW_TEST_DOCTOR_PASSWORD'),
  },
  {
    label: '患者',
    username: 'gc_patient_test_20260823',
    password: required('GERCLAW_TEST_PATIENT_PASSWORD'),
  },
]

interface Tripwire {
  consoleErrors: string[]
  pageErrors: string[]
  failedRequests: string[]
}

const watch = (page: Page): Tripwire => {
  const tripwire: Tripwire = { consoleErrors: [], pageErrors: [], failedRequests: [] }
  page.on('console', (message) => {
    if (message.type() === 'error') tripwire.consoleErrors.push(message.text())
  })
  page.on('pageerror', error => tripwire.pageErrors.push(error.message))
  page.on('requestfailed', (request) => {
    const failure = request.failure()?.errorText ?? 'unknown'
    if (!failure.includes('ERR_ABORTED')) tripwire.failedRequests.push(`${request.method()} ${request.url()}: ${failure}`)
  })
  return tripwire
}

const assertClean = (tripwire: Tripwire): void => {
  expect(tripwire.consoleErrors).toEqual([])
  expect(tripwire.pageErrors).toEqual([])
  expect(tripwire.failedRequests).toEqual([])
}

const visible = async (locator: Locator, timeout = 30_000): Promise<void> => {
  await locator.waitFor({ state: 'visible', timeout })
}

const containsText = async (
  locator: Locator,
  expected: string | RegExp,
  timeout = 30_000,
): Promise<void> => {
  await expect.poll(() => locator.textContent(), { timeout }).toMatch(expected)
}

const hasAttribute = async (
  locator: Locator,
  name: string,
  expected: string | RegExp,
  timeout = 30_000,
): Promise<void> => {
  await expect.poll(() => locator.getAttribute(name), { timeout }).toMatch(expected)
}

const waitForWorkspace = async (page: Page): Promise<void> => {
  await page.waitForURL(url => url.origin === BASE_URL && !url.pathname.startsWith('/auth/'), { timeout: 60_000 })
  await page.getByRole('button', { name: '健康对话' }).waitFor({ timeout: 60_000 })
  await page.locator('[data-composer-card] textarea').waitFor({ timeout: 60_000 })
}

const login = async (page: Page, identity: Identity): Promise<void> => {
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' })
  await page.getByLabel('用户名').fill(identity.username)
  await page.getByLabel('密码').fill(identity.password)
  await page.getByRole('button', { name: '进入健康工作台' }).click()
  await waitForWorkspace(page)
}

const enterAsGuest = async (page: Page): Promise<void> => {
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /游客体验/u }).click()
  await waitForWorkspace(page)
}

const logout = async (page: Page): Promise<void> => {
  await page.getByRole('button', { name: '设置' }).click()
  const dialog = page.getByRole('dialog', { name: '设置' })
  await dialog.getByRole('button', { name: '退出当前账号' }).click()
  await page.getByRole('heading', { name: 'GerClaw', level: 1 }).waitFor({ timeout: 30_000 })
}

const forceLogout = async (page: Page): Promise<void> => {
  if (page.isClosed() || !page.url().startsWith(BASE_URL)) return
  await page.evaluate(async () => {
    await fetch('/auth/logout', { method: 'POST' })
  }).catch(() => undefined)
}

const composer = (page: Page) => page.locator('[data-composer-card] textarea')

const sendChat = async (page: Page, prompt: string, timeout = 180_000): Promise<void> => {
  const before = await page.locator('button[data-gerclaw-read-aloud]').count()
  await composer(page).fill(prompt)
  await composer(page).press('Enter')
  await expect.poll(
    () => page.locator('button[data-gerclaw-read-aloud]').count(),
    { timeout },
  ).toBeGreaterThan(before)
}

const sendInteractiveChat = async (
  page: Page,
  prompt: string,
  timeout = 240_000,
): Promise<void> => {
  const before = await page.locator('button[data-gerclaw-read-aloud]').count()
  await composer(page).fill(prompt)
  await composer(page).press('Enter')
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    if (await page.locator('button[data-gerclaw-read-aloud]').count() > before) return
    const question = page.locator('[data-question-key]')
    if (await question.isVisible().catch(() => false)) {
      const answer = question.getByRole('textbox').last()
      await answer.fill('请根据我已经提供的信息继续，必要时给出可填写的示例。')
      await answer.press('Enter')
    }
    await page.waitForTimeout(250)
  }
  throw new Error(`交互式健康能力在 ${timeout}ms 内没有完成：${prompt}`)
}

const closeDialog = async (dialog: Locator): Promise<void> => {
  await dialog.getByRole('button', { name: '关闭' }).click()
  await expect.poll(() => dialog.count()).toBe(0)
}

const expectTaskResult = async (dialog: Locator, timeout = 180_000): Promise<void> => {
  await dialog.locator('[data-gerclaw-final]').waitFor({ timeout })
  expect(await dialog.locator('[data-gerclaw-step]').count()).toBeGreaterThan(0)
  await visible(dialog.getByText(/总用时/u))
  await visible(dialog.getByText('最终结果'))
}

const runCga = async (page: Page, kind: string): Promise<void> => {
  await page.getByRole('button', { name: '综合量表' }).click()
  const dialog = page.getByRole('dialog', { name: '综合量表' })
  await dialog.getByLabel('选择量表').selectOption(kind)
  await dialog.getByRole('button', { name: '完成确定性计分' }).click()
  await expectTaskResult(dialog)
  await closeDialog(dialog)
}

const openMore = async (page: Page, name: string): Promise<Locator> => {
  await page.getByRole('button', { name: '更多' }).click()
  const more = page.getByRole('dialog', { name: '更多健康服务' })
  await more.getByRole('button', { name: new RegExp(name, 'u') }).click()
  return page.getByRole('dialog')
}

const runMedicalTasks = async (page: Page): Promise<void> => {
  for (const kind of ['phq9', 'sas', 'psqi', 'minicog', 'mmse']) await runCga(page, kind)

  await page.getByRole('button', { name: '用药核对' }).click()
  let dialog = page.getByRole('dialog', { name: '用药核对' })
  await dialog.getByLabel(/年龄/u).fill('75')
  await dialog.getByRole('button', { name: '开始核对' }).click()
  await expectTaskResult(dialog)
  await visible(dialog.getByText(/相互作用|高风险/u).first())
  await closeDialog(dialog)

  await page.getByRole('button', { name: '健康档案' }).click()
  dialog = page.getByRole('dialog', { name: '健康档案' })
  await dialog.getByLabel('称呼').fill('E2E 健康用户')
  await dialog.getByLabel('年龄').fill('75')
  await dialog.getByLabel('已有疾病').fill('高血压')
  await dialog.getByLabel('当前用药').fill('阿司匹林')
  await dialog.getByLabel('健康目标').fill('改善睡眠')
  await dialog.getByRole('button', { name: '保存健康档案' }).click()
  await expectTaskResult(dialog)
  await closeDialog(dialog)

  dialog = await openMore(page, '慢病记录')
  await dialog.getByLabel('数值').fill('138')
  await dialog.getByRole('button', { name: '保存测量' }).click()
  await expectTaskResult(dialog)
  await closeDialog(dialog)

  dialog = await openMore(page, '暖心陪伴')
  await dialog.getByLabel('此刻想说的话').fill('今天有些孤单，希望有人陪我聊聊。')
  await dialog.getByRole('button', { name: '和我聊聊' }).click()
  await expectTaskResult(dialog)
  await closeDialog(dialog)

  dialog = await openMore(page, '风险提醒')
  await visible(dialog.getByText(/汇总量表/u))
  await closeDialog(dialog)

  dialog = await openMore(page, '文档库')
  await dialog.getByLabel('添加到我的文档库').setInputFiles(DOCUMENT_FIXTURE)
  await containsText(dialog.getByRole('status'), '已加入', 60_000)
  await dialog.getByLabel('检索词').fill('老年高血压睡眠管理')
  await dialog.getByRole('button', { name: '检索本地与医学资料' }).click()
  await expectTaskResult(dialog, 240_000)
  const sourceLinks = await dialog.getByRole('link', { name: '打开原文' }).all()
  expect(sourceLinks.length).toBeGreaterThanOrEqual(3)
  const hrefs = await Promise.all(sourceLinks.map(link => link.getAttribute('href')))
  expect(hrefs.some(href => href?.includes('pubmed.ncbi.nlm.nih.gov'))).toBe(true)
  expect(hrefs.some(href => href?.includes('fda.gov'))).toBe(true)
  expect(hrefs.some(href => href?.includes('medlineplus.gov'))).toBe(true)
  await dialog.getByRole('button', { name: '导出七种格式' }).click()
  await containsText(dialog.getByRole('status'), '已生成 7 个格式', 120_000)
  await closeDialog(dialog)

  await expect.poll(() => page.locator('[data-gerclaw-artifact-layout] li').count(), { timeout: 30_000 }).toBeGreaterThanOrEqual(7)
  await hasAttribute(page.locator('[data-gerclaw-artifact-preview] a'), 'href', /\/gerclaw\/api\/artifacts\//u)
}

const runVoice = async (page: Page): Promise<void> => {
  const upload = page.getByRole('button', { name: '上传音频进行识别' })
  const picker = upload.locator('xpath=following-sibling::input[@type="file"]')
  await picker.setInputFiles(AUDIO_FIXTURE)
  await visible(page.getByRole('status').filter({ hasText: /已完成转写/u }), 120_000)
  await visible(page.getByText('我今年七十五岁，最近晚上睡不好，正在服用阿司匹林。', { exact: true }), 120_000)
  const read = page.locator('button[data-gerclaw-read-aloud]').last()
  await read.click()
  await hasAttribute(read, 'aria-label', '停止朗读', 60_000)
  await read.click()
  await hasAttribute(read, 'aria-label', '朗读这条回复')
  await read.click()
  await hasAttribute(read, 'aria-label', '停止朗读', 60_000)
  await composer(page).fill('输入打断朗读')
  await hasAttribute(read, 'aria-label', '朗读这条回复')
  await composer(page).fill('')

  const mic = page.getByRole('button', { name: '开始语音输入' })
  await mic.click()
  await visible(page.getByRole('button', { name: '停止录音并发送' }))
  await page.getByRole('button', { name: '取消语音输入' }).click()
  await visible(page.getByText('已取消录音', { exact: true }))
}

const runPlanGoalAndSkills = async (page: Page): Promise<void> => {
  await page.getByRole('button', { name: '能力' }).click()
  for (const name of ['随访问卷', '风险评估', '健康教育', '用药提醒'])
    await visible(page.getByText(name, { exact: true }).first())
  await page.keyboard.press('Escape')

  for (const command of [
    '/followup 请给我一个一题的随访问卷',
    '/risk-assessment 请简要评估跌倒风险',
    '/health-education 请说明每日步行注意事项',
    '/medication-reminder 请给出阿司匹林每日一次的提醒模板',
  ]) await sendInteractiveChat(page, command)

  for (const prompt of [
    '请自然调用随访问卷能力，只问我一个随访问题。',
    '请自然调用风险评估能力，简要评估我的睡眠风险。',
    '请自然调用健康教育能力，说明老年人补水注意事项。',
    '请自然调用用药提醒能力，生成阿司匹林每日一次的提醒。',
  ]) await sendInteractiveChat(page, prompt)

  const before = await page.locator('button[data-gerclaw-read-aloud]').count()
  await composer(page).fill('/plan 为未来三天制定一个不超过三步的健康记录计划，并提交审核。')
  await composer(page).press('Enter')
  const review = page.locator('[data-plan-review-key]')
  await review.waitFor({ timeout: 180_000 })
  await visible(review.getByRole('button', { name: /确认执行/u }))
  await review.getByRole('button', { name: /确认执行/u }).click()
  await expect.poll(() => page.locator('button[data-gerclaw-read-aloud]').count(), { timeout: 180_000 }).toBeGreaterThan(before)

  await sendChat(page, '/goal 建立一个持续记录血压的健康目标')
  const goal = page.locator('[data-goal-bar]')
  await goal.waitFor({ timeout: 30_000 })
  await containsText(goal, /记录血压/u)
  for (const name of [/暂停/u, /恢复/u]) {
    const action = goal.getByRole('button', { name })
    if (await action.count()) await action.click()
  }
}

const runPrescription = async (page: Page): Promise<void> => {
  const before = await page.locator('[data-gerclaw-conversation-task]').count()
  await page.getByRole('button', { name: '五大处方' }).click()
  await visible(page.getByText(/最希望改善|健康目标/u).last(), 180_000)
  await sendChat(page, '我的健康目标是改善睡眠。')
  await sendChat(page, '我最近夜间易醒，正在服用阿司匹林每日一次，没有已知药物过敏。', 240_000)
  await expect.poll(() => page.locator('[data-gerclaw-conversation-task]').count(), { timeout: 240_000 }).toBe(before + 1)
  const card = page.locator('[data-gerclaw-conversation-task]').last()
  for (const chapter of ['药物处方', '运动处方', '营养处方', '心理处方', '康复处方'])
    await visible(card.getByText(chapter, { exact: true }).first())
  expect(await page.getByText(/独立处方表单/u).count()).toBe(0)
}

const assertProductBaseline = async (page: Page): Promise<void> => {
  const sidebarToggle = page.getByRole('button', { name: '打开侧边栏' })
  const sidebarWasCollapsed = await sidebarToggle.isVisible().catch(() => false)
  if (sidebarWasCollapsed) await sidebarToggle.click()
  await visible(page.getByText('GerClaw', { exact: true }).first())
  await visible(page.getByText('老年慢病智慧诊疗助手', { exact: true }).first())
  await visible(composer(page))
  const box = await composer(page).boundingBox()
  const viewport = page.viewportSize()
  expect(box).not.toBeNull()
  expect(viewport).not.toBeNull()
  expect((box?.y ?? 0) + (box?.height ?? 0)).toBeGreaterThan((viewport?.height ?? 0) * 0.72)
  expect(await page.getByText(/DeepSeek Harness|插件管理|终端/u).count()).toBe(0)
  for (const name of ['健康对话', '五大处方', '综合量表', '用药核对', '健康档案', '更多', '设置']) {
    const button = page.getByRole('button', { name })
    await hasAttribute(button, 'aria-label', name)
  }
  if (sidebarWasCollapsed) {
    await page.getByRole('button', { name: '收起侧边栏' }).click()
    await visible(composer(page))
  }
  const artifacts = page.getByRole('region', { name: '产物' })
  if ((viewport?.width ?? 0) < 768) {
    await expect.poll(() => artifacts.isVisible()).toBe(false)
  } else {
    await visible(artifacts)
  }
}

const runIdentityMatrix = async (page: Page): Promise<void> => {
  await assertProductBaseline(page)
  await sendChat(page, '请用二级标题、加粗文字和三项列表回答：老年人今天如何安全记录血压？')
  expect(await page.locator('pre').filter({ hasText: /老年人今天/u }).count()).toBe(0)
  await runVoice(page)
  await runPlanGoalAndSkills(page)
  await runPrescription(page)
  await runMedicalTasks(page)
}

describe.skipIf(!ENABLED)('GerClaw 正式 Gateway 全功能真实 E2E', { concurrent: false }, () => {
  let browser: Browser
  const contexts: BrowserContext[] = []

  beforeAll(async () => {
    identities()
    const response = await fetch(BASE_URL)
    if (!response.ok) throw new Error(`GerClaw Gateway 未就绪：HTTP ${response.status}`)
    browser = await chromium.launch({
      headless: true,
      args: [
        '--use-fake-ui-for-media-stream',
        '--use-fake-device-for-media-stream',
        `--use-file-for-fake-audio-capture=${AUDIO_FIXTURE}`,
      ],
    })
  }, 60_000)

  afterAll(async () => {
    await Promise.all(contexts.flatMap(context => context.pages().map(forceLogout)))
    await Promise.all(contexts.map(context => context.close()))
    await browser?.close()
  })

  it('通过真实注册页完成注册、一次性恢复码重置、登录和退出', async () => {
    const context = await browser.newContext({ locale: 'zh-CN', viewport: { width: 1280, height: 900 } })
    contexts.push(context)
    const page = await context.newPage()
    const tripwire = watch(page)
    const username = `gc_recovery_e2e_${Date.now()}`
    const initialPassword = randomBytes(18).toString('base64url')
    const recoveredPassword = randomBytes(18).toString('base64url')
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: '注册' }).click()
    await page.getByLabel('用户名').fill(username)
    await page.getByLabel('密码').fill(initialPassword)
    await page.getByLabel('称呼偏好').selectOption('doctor')
    await page.getByRole('button', { name: '进入健康工作台' }).click()
    const recovery = page.locator('#recovery')
    await containsText(recovery, '一次性恢复码')
    const recoveryCode = (await recovery.textContent())?.split('：')[1]?.split('。')[0]?.trim()
    expect(recoveryCode).toBeTruthy()
    await waitForWorkspace(page)
    await logout(page)

    await page.getByRole('button', { name: '重置密码' }).click()
    await page.getByLabel('用户名').fill(username)
    await page.getByLabel('密码').fill(recoveredPassword)
    await page.getByLabel('恢复码').fill(recoveryCode!)
    await page.getByRole('button', { name: '进入健康工作台' }).click()
    await containsText(recovery, '一次性恢复码')
    await page.waitForTimeout(6_500)
    await page.getByLabel('用户名').fill(username)
    await page.getByLabel('密码').fill(recoveredPassword)
    await page.getByRole('button', { name: '进入健康工作台' }).click()
    await waitForWorkspace(page)
    await logout(page)
    assertClean(tripwire)
  }, 180_000)

  for (const identity of ['doctor', 'patient'] as const) {
    it(`${identity === 'doctor' ? '医生' : '患者'}账号完整真实路径`, async () => {
      const selected = identities()[identity === 'doctor' ? 0 : 1]!
      const context = await browser.newContext({ locale: 'zh-CN', permissions: ['microphone'], viewport: { width: 1440, height: 960 } })
      contexts.push(context)
      const page = await context.newPage()
      const tripwire = watch(page)
      onTestFailed(() => { void page.screenshot({ path: `.artifacts/gerclaw-${identity}-failed.png`, fullPage: true }) })
      await login(page, selected)
      await runIdentityMatrix(page)
      await logout(page)
      assertClean(tripwire)
    }, 2_400_000)
  }

  it('游客完整真实路径并在退出后清理', async () => {
    const context = await browser.newContext({ locale: 'zh-CN', permissions: ['microphone'], viewport: { width: 1280, height: 900 } })
    contexts.push(context)
    const page = await context.newPage()
    const tripwire = watch(page)
    onTestFailed(() => { void page.screenshot({ path: '.artifacts/gerclaw-guest-failed.png', fullPage: true }) })
    await enterAsGuest(page)
    await runIdentityMatrix(page)
    await logout(page)
    assertClean(tripwire)
  }, 2_400_000)

  it('拒绝跨账号会话、文件、产物、下载与 WebSocket 标识', async () => {
    const [doctor, patient] = identities()
    const doctorContext = await browser.newContext({ locale: 'zh-CN' })
    const patientContext = await browser.newContext({ locale: 'zh-CN' })
    contexts.push(doctorContext, patientContext)
    const doctorPage = await doctorContext.newPage()
    const patientPage = await patientContext.newPage()
    await login(doctorPage, doctor!)
    await login(patientPage, patient!)
    const doctorBootstrap = await doctorPage.evaluate(async () => {
      const response = await fetch('/gerclaw/api/bootstrap')
      return JSON.parse(await response.text()) as unknown
    }) as {
      artifacts?: Array<{ artifactId: string }>
      documents?: Array<{ documentId: string }>
      tasks?: Array<{ taskId: string; sessionId?: string }>
    }
    const ids = {
      artifact: doctorBootstrap.artifacts?.[0]?.artifactId,
      document: doctorBootstrap.documents?.[0]?.documentId,
      task: doctorBootstrap.tasks?.[0]?.taskId,
      session: doctorBootstrap.tasks?.find(task => task.sessionId)?.sessionId,
    }
    expect(ids.artifact && ids.document && ids.task && ids.session).toBeTruthy()
    for (const path of [
      `/gerclaw/api/artifacts/${ids.artifact}`,
      `/gerclaw/api/documents/${ids.document}`,
    ]) {
      const status = await patientPage.evaluate(async target => (await fetch(target)).status, path)
      expect(status).toBe(400)
    }
    const bootstrap = await patientPage.evaluate(async (sessionId) => {
      const response = await fetch('/gerclaw/api/bootstrap', { headers: { 'x-gerclaw-session-id': String(sessionId) } })
      return { status: response.status, body: JSON.parse(await response.text()) as unknown }
    }, ids.session)
    expect(bootstrap.status).toBe(200)
    expect(JSON.stringify(bootstrap.body)).not.toContain(String(ids.task))
    const wsClosed = await patientPage.evaluate(sessionId => new Promise<boolean>((resolve) => {
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const socket = new WebSocket(`${protocol}//${location.host}/gerclaw/api/voice/asr-stream?sessionId=${encodeURIComponent(String(sessionId))}`)
      const timer = setTimeout(() => { socket.close(); resolve(false) }, 5_000)
      socket.addEventListener('close', () => { clearTimeout(timer); resolve(true) })
      socket.addEventListener('message', () => { clearTimeout(timer); socket.close(); resolve(false) })
    }), ids.session)
    expect(wsClosed).toBe(true)
    await logout(doctorPage)
    await logout(patientPage)
  }, 180_000)

  for (const [name, viewport] of Object.entries({
    desktop: { width: 1440, height: 960 },
    tablet: { width: 900, height: 1100 },
    mobile: { width: 390, height: 844 },
  })) {
    it(`${name} 布局、键盘焦点、tooltip 与无横向溢出`, async () => {
      const context = await browser.newContext({ locale: 'zh-CN', viewport })
      contexts.push(context)
      const page = await context.newPage()
      await enterAsGuest(page)
      await assertProductBaseline(page)
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
      expect(overflow).toBeLessThanOrEqual(1)
      const health = page.getByRole('button', { name: '健康对话' })
      await health.focus()
      expect(await health.evaluate(element => element === document.activeElement)).toBe(true)
      await health.hover()
      await visible(page.getByText('健康对话', { exact: true }).first())
      await logout(page)
    })
  }
})
