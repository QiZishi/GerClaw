import type { Browser, BrowserContext, Locator, Page } from 'playwright'
import { chromium } from 'playwright'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

/**
 * A small, credential-free browser gate for the product shell.
 *
 * This intentionally uses the real Gateway and its real guest Host. It does
 * not mock Loader, the client bundle, or any browser service. The expensive
 * model/medical matrix remains in gerclaw-real.e2e.ts; this file protects the
 * visible product contract on every UI change.
 */
const BASE_URL = process.env.GERCLAW_E2E_BASE_URL ?? 'http://127.0.0.1:3000'
const ENABLED = process.env.GERCLAW_BASELINE_E2E === '1'
const FAILURE_RECOVERY = process.env.GERCLAW_FAILURE_E2E === '1'

const viewports = {
  desktop: { width: 1440, height: 960 },
  tablet: { width: 900, height: 1100 },
  mobile: { width: 390, height: 844 },
} as const

interface BrowserTripwire {
  errors: string[]
  warnings: string[]
}

const watchConsole = (page: Page): BrowserTripwire => {
  const tripwire: BrowserTripwire = { errors: [], warnings: [] }
  page.on('console', (message) => {
    if (message.type() === 'error') tripwire.errors.push(message.text())
    if (message.type() === 'warning') tripwire.warnings.push(message.text())
  })
  page.on('pageerror', error => tripwire.errors.push(`pageerror: ${error.message}`))
  return tripwire
}

const assertConsoleClean = (tripwire: BrowserTripwire): void => {
  expect(tripwire.errors).toEqual([])
  expect(tripwire.warnings.filter(message => /agent-preset-not-found/u.test(message))).toEqual([])
}

const waitForWorkspace = async (page: Page): Promise<void> => {
  await page.locator('[data-composer-card] textarea').waitFor({ timeout: 90_000 })
  await page.getByRole('button', { name: '开始语音输入' }).waitFor({ timeout: 30_000 })
  expect(await page.title()).toBe('GerClaw｜老年慢病智慧诊疗助手')
}

const enterAsGuest = async (page: Page): Promise<void> => {
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /游客体验/u }).click()
  await waitForWorkspace(page)
}

const expandResponsiveSidebar = async (page: Page): Promise<void> => {
  const viewport = page.viewportSize()
  if ((viewport?.width ?? 0) >= 1200) return
  const toggle = page.getByRole('button', { name: /^(?:打开|展开)侧边栏$/u }).first()
  if (!await toggle.isVisible()) return
  await toggle.waitFor({ state: 'visible', timeout: 30_000 })
  await toggle.click()
  await page.locator('[data-gerclaw-brand-name]').first().waitFor({ state: 'visible', timeout: 30_000 })
}

const collapseResponsiveSidebar = async (page: Page): Promise<void> => {
  const viewport = page.viewportSize()
  if ((viewport?.width ?? 0) >= 1200) return
  const toggle = page.getByRole('button', { name: '收起侧边栏', exact: true }).first()
  if (!await toggle.isVisible()) return
  await toggle.click()
  await page.getByRole('button', { name: /^(?:打开|展开)侧边栏$/u }).first()
    .waitFor({ state: 'visible', timeout: 30_000 })
}

const cleanupGuest = async (page: Page): Promise<void> => {
  await page.evaluate(async () => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => controller.abort(), 15_000)
    try {
      await fetch('/auth/logout', { method: 'POST', signal: controller.signal })
    } finally {
      window.clearTimeout(timer)
    }
  }).catch(() => undefined)
}

const assertNoInternalBrand = async (page: Page): Promise<void> => {
  const visibleText = await page.locator('body').innerText()
  expect(visibleText).not.toMatch(/DeepSeek|DeepSeek Harness|\bDSH\b|插件管理|终端|开发者工具/u)
  expect(await page.title()).toBe('GerClaw｜老年慢病智慧诊疗助手')
}

const assertBrandGeometry = async (page: Page): Promise<void> => {
  const viewport = page.viewportSize()
  expect(viewport).not.toBeNull()
  const brandName = page.locator('[data-gerclaw-brand-name]').first()
  const logo = page.locator('[data-gerclaw-logo]').first()
  await brandName.waitFor({ state: 'visible' })
  await logo.waitFor({ state: 'visible' })
  for (const locator of [brandName, logo]) {
    const box = await locator.boundingBox()
    expect(box).not.toBeNull()
    expect(box?.width ?? 0).toBeGreaterThan(0)
    expect(box?.height ?? 0).toBeGreaterThan(0)
    expect(box?.y ?? -1).toBeGreaterThanOrEqual(0)
    expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(viewport!.height + 1)
  }
  await page.getByText('GerClaw', { exact: true }).first().waitFor({ state: 'visible' })
  await page.getByText('老年慢病智慧诊疗助手', { exact: true }).first().waitFor({ state: 'visible' })
}

const assertNavigation = async (page: Page): Promise<void> => {
  const medicalNames = ['五大处方', '综合量表', '用药核对', '健康档案', '更多']
  for (const name of [...medicalNames, '设置']) {
    const button = page.getByRole('button', { name, exact: true })
    await button.waitFor({ state: 'visible' })
    expect(await button.getAttribute('aria-label')).toBe(name)
    await button.hover()
  }
  expect(await page.getByRole('button', { name: '健康对话', exact: true }).count()).toBe(0)

  const medicalBoxes = await Promise.all(medicalNames.map(name =>
    page.getByRole('button', { name, exact: true }).boundingBox()))
  for (let index = 1; index < medicalBoxes.length; index++) {
    expect(medicalBoxes[index]?.y ?? -Infinity)
      .toBeGreaterThan((medicalBoxes[index - 1]?.y ?? 0) + (medicalBoxes[index - 1]?.height ?? 0) - 1)
  }

  // New/search are native sidebar controls. Their labels are part of the
  // GerClaw user contract even though the surrounding layout remains native.
  const newConversation = page.getByRole('button', { name: '新建会话', exact: true }).first()
  const search = page.getByRole('button', { name: '搜索会话', exact: true })
  await newConversation.waitFor({ state: 'visible' })
  await search.waitFor({ state: 'visible' })
  expect(await newConversation.getAttribute('aria-label')).toBe('新建会话')
  expect(await search.getAttribute('aria-label')).toBe('搜索会话')
  const newBox = await newConversation.boundingBox()
  const searchBox = await search.boundingBox()
  expect(newBox).not.toBeNull()
  expect(searchBox).not.toBeNull()

  // Native history remains the navigation owner; GerClaw contributes only
  // its public medical-action and settings slots.
  const action = page.locator('[data-gerclaw-medical-nav]').first()
  const history = page.getByRole('tree', { name: '会话' }).first()
  const settings = page.locator('[data-gerclaw-settings-trigger]').first()
  await action.waitFor({ state: 'visible' })
  await history.waitFor({ state: 'visible' })
  await settings.waitFor({ state: 'visible' })
  const [actionBox, historyBox, settingsBox] = await Promise.all([
    action.boundingBox(),
    history.boundingBox(),
    settings.boundingBox(),
  ])
  expect(historyBox?.y ?? -Infinity).toBeGreaterThanOrEqual(searchBox?.y ?? 0)
  expect(settingsBox?.y ?? 0).toBeGreaterThanOrEqual(actionBox?.y ?? 0)
  expect(await page.locator('body').innerText()).not.toMatch(/工作区|选择工作区|添加工作区/u)
}

const assertComposer = async (page: Page): Promise<void> => {
  const composer = page.locator('[data-composer-card] textarea')
  const uploadButton = page.getByRole('button', { name: '上传文件', exact: true })
  const micButton = page.getByRole('button', { name: '开始语音输入', exact: true })
  const sendButton = page.getByRole('button', { name: '发送消息', exact: true })
  await uploadButton.waitFor({ state: 'visible' })
  await micButton.waitFor({ state: 'visible' })
  await sendButton.waitFor({ state: 'visible' })
  const fileInput = page.locator('[data-gerclaw-composer-document] input[type="file"]')
  expect(await fileInput.getAttribute('accept')).toContain('audio/*')
  expect(await page.getByRole('button', { name: '上传音频进行识别', exact: true }).count()).toBe(0)
  await expect.poll(async () => {
    const [mic, send] = await Promise.all([micButton.boundingBox(), sendButton.boundingBox()])
    return (mic?.x ?? Infinity) < (send?.x ?? -Infinity)
  }, { timeout: 2_000 }).toBe(true)
  const [uploadBox, micBox, sendBox] = await Promise.all([
    uploadButton.boundingBox(), micButton.boundingBox(), sendButton.boundingBox(),
  ])
  expect(uploadBox?.x ?? Infinity).toBeLessThan(micBox?.x ?? -Infinity)
  expect(micBox?.x ?? Infinity).toBeLessThan(sendBox?.x ?? -Infinity)
  const box = await composer.boundingBox()
  const viewport = page.viewportSize()
  expect(box).not.toBeNull()
  expect((box?.y ?? 0) + (box?.height ?? 0)).toBeGreaterThan((viewport?.height ?? 0) * 0.72)

  for (const control of [uploadButton, micButton, sendButton, page.getByRole('button', { name: '计划与健康能力' })]) {
    const controlBox = await control.boundingBox()
    expect(controlBox?.width ?? 0).toBeGreaterThanOrEqual(44)
    expect(controlBox?.height ?? 0).toBeGreaterThanOrEqual(44)
  }

  await page.locator('body').click({ position: { x: 1, y: 1 } })
  for (let index = 0; index < 40 && !(await composer.evaluate(element => element === document.activeElement)); index += 1)
    await page.keyboard.press('Tab')
  expect(await composer.evaluate(element => element === document.activeElement && element.matches(':focus-visible'))).toBe(true)
}

describe.skipIf(!ENABLED)('GerClaw 前端受保护基线（真实 Gateway）', { concurrent: false }, () => {
  let browser: Browser
  const contexts: BrowserContext[] = []

  beforeAll(async () => {
    const response = await fetch(BASE_URL)
    if (!response.ok) throw new Error(`GerClaw Gateway 未就绪：HTTP ${response.status}`)
    browser = await chromium.launch({ headless: true })
  }, 120_000)

  afterAll(async () => {
    await Promise.all(contexts.flatMap(context => context.pages().map(cleanupGuest)))
    await Promise.all(contexts.map(context => context.close()))
    await browser?.close()
  })

  it('登录页保留 GerClaw 品牌和产品亮点', async () => {
    const context = await browser.newContext({ locale: 'zh-CN', viewport: viewports.desktop })
    contexts.push(context)
    const page = await context.newPage()
    const tripwire = watchConsole(page)
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' })
    expect(await page.title()).toBe('GerClaw｜老年慢病智慧诊疗助手')
    await page.locator('img[alt="GerClaw 品牌图标"]').waitFor({ state: 'visible' })
    await page.getByText('GerClaw', { exact: true }).waitFor({ state: 'visible' })
    await page.getByText('老年慢病智慧诊疗助手', { exact: true }).waitFor({ state: 'visible' })
    for (const text of [
      '对话收集资料，生成药物、运动、营养、心理和康复处方',
      '完成五类老年综合评估，联动用药核对与风险提醒',
      '支持语音与病历资料解析，结合本地医学知识库提供可追溯依据',
    ]) await page.getByText(text, { exact: true }).waitFor({ state: 'visible' })
    await assertNoInternalBrand(page)
    assertConsoleClean(tripwire)
  })

  for (const [name, viewport] of Object.entries(viewports)) {
    it(`${name} 工作台保持品牌、布局与中文辅助信息`, async () => {
      const context = await browser.newContext({ locale: 'zh-CN', viewport })
      contexts.push(context)
      const page = await context.newPage()
      const tripwire = watchConsole(page)
      await enterAsGuest(page)
      await expandResponsiveSidebar(page)
      await assertBrandGeometry(page)
      await assertNoInternalBrand(page)
      await assertNavigation(page)
      await collapseResponsiveSidebar(page)
      await assertComposer(page)
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
      expect(overflow).toBeLessThanOrEqual(1)
      expect(await page.locator('[data-gerclaw-prescription-form]').count()).toBe(0)
      expect(await page.getByText('独立处方表单', { exact: true }).count()).toBe(0)
      assertConsoleClean(tripwire)
      await cleanupGuest(page)
    })
  }

  it('双倍系统缩放下主对话仍可重排且无横向溢出', async () => {
    const context = await browser.newContext({
      locale: 'zh-CN',
      viewport: viewports.desktop,
      deviceScaleFactor: 2,
    })
    contexts.push(context)
    const page = await context.newPage()
    const tripwire = watchConsole(page)
    await enterAsGuest(page)
    await page.evaluate(() => { document.documentElement.style.zoom = '2' })
    await expect.poll(
      () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth),
      { timeout: 2_000 },
    ).toBeLessThanOrEqual(1)
    await page.locator('[data-composer-card] textarea').waitFor({ state: 'visible' })
    assertConsoleClean(tripwire)
    await cleanupGuest(page)
  })

  it.skipIf(!FAILURE_RECOVERY)('主模型连接失败时保留用户消息并显示可恢复中文提示', async () => {
    const context = await browser.newContext({ locale: 'zh-CN', viewport: viewports.desktop })
    contexts.push(context)
    const page = await context.newPage()
    await enterAsGuest(page)
    const prompt = '请帮我记录今天的血压情况。'
    const input = page.locator('[data-composer-card] textarea')
    await input.fill(prompt)
    await input.press('Enter')
    await page.getByText('暂时无法连接健康助手', { exact: true }).waitFor({ timeout: 90_000 })
    await page.locator('[data-chat-flow-kind="user"]').getByText(prompt, { exact: true }).waitFor()
    await page.getByText('刚才的内容仍在当前对话中，请稍后重试。', { exact: true }).waitFor()
    expect(await page.locator('body').innerText()).not.toMatch(/ECONNREFUSED|127\.0\.0\.1:9|fetch failed/u)
    expect(await page.getByText('GerClaw 主模型', { exact: true }).count()).toBe(1)
    await input.fill('稍后重试时仍可继续输入。')
    expect(await input.inputValue()).toBe('稍后重试时仍可继续输入。')
    await cleanupGuest(page)
  })

  it('游客通过中文入口完成主对话、目标管理与计划审核', async () => {
    const context = await browser.newContext({ locale: 'zh-CN', viewport: viewports.desktop })
    contexts.push(context)
    const page = await context.newPage()
    const tripwire = watchConsole(page)
    await enterAsGuest(page)

    expect(await page.getByRole('button', { name: '命令', exact: true }).isVisible().catch(() => false)).toBe(false)
    const before = await page.locator('button[data-gerclaw-read-aloud]').count()
    const input = page.locator('[data-composer-card] textarea')
    await input.fill('请只用一句中文告诉我今天记录血压最重要的一点。')
    await input.press('Enter')
    await expect.poll(
      () => page.locator('button[data-gerclaw-read-aloud]').count(),
      { timeout: 180_000 },
    ).toBeGreaterThan(before)
    expect(await page.locator('[data-variant="think"]:visible').count()).toBe(0)

    const openCapabilities = async (): Promise<Locator> => {
      await page.getByRole('button', { name: '计划与健康能力' }).click()
      const dialog = page.getByRole('dialog', { name: '计划与健康能力' })
      await dialog.waitFor({ state: 'visible' })
      for (const name of ['制定计划', '建立目标', '随访问卷', '风险评估', '健康教育', '用药提醒'])
        await dialog.getByRole('button', { name }).waitFor({ state: 'visible' })
      return dialog
    }

    let dialog = await openCapabilities()
    await dialog.getByLabel('我想完成什么').fill('持续记录早晚血压并观察趋势')
    await dialog.getByRole('button', { name: '建立目标' }).click()
    const goal = page.locator('[data-goal-bar]')
    await goal.waitFor({ timeout: 30_000 })
    await goal.getByText('持续记录早晚血压并观察趋势', { exact: true }).waitFor()
    await goal.getByRole('button', { name: /暂停/u }).click()
    await goal.getByRole('button', { name: /恢复/u }).waitFor()
    await goal.getByRole('button', { name: /恢复/u }).click()
    await goal.getByRole('button', { name: /编辑/u }).click()
    await goal.getByLabel('目标内容').fill('每天早晚记录血压')
    await goal.getByRole('button', { name: /保存/u }).click()
    await goal.getByText('每天早晚记录血压', { exact: true }).waitFor()
    await goal.getByRole('button', { name: /清除/u }).click()
    await goal.waitFor({ state: 'detached', timeout: 30_000 })

    dialog = await openCapabilities()
    await dialog.getByLabel('我想完成什么').fill('未来三天早晚记录血压，总共不超过三步')
    await dialog.getByRole('button', { name: '制定计划' }).click()
    const review = page.locator('[data-plan-review-key]')
    const deadline = Date.now() + 180_000
    while (Date.now() < deadline && !(await review.isVisible().catch(() => false))) {
      const question = page.locator('[data-question-key]')
      if (await question.isVisible().catch(() => false)) {
        const answers = question.getByRole('textbox')
        for (let index = 0; index < await answers.count(); index += 1)
          await answers.nth(index).fill('无需补充，请按通用健康记录方案继续。')
        if (await answers.count()) await answers.last().press('Enter')
      }
      await page.waitForTimeout(250)
    }
    await review.waitFor({ timeout: 1_000 })
    await review.getByRole('button', { name: /确认执行/u }).waitFor()
    assertConsoleClean(tripwire)
    await cleanupGuest(page)
  }, 300_000)
})
