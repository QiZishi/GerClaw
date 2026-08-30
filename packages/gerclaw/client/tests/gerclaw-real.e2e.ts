import { readdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Browser, BrowserContext, Locator, Page } from 'playwright'
import { chromium } from 'playwright'
import { afterAll, beforeAll, describe, expect, it, onTestFailed } from 'vitest'

const BASE_URL = process.env.GERCLAW_E2E_BASE_URL ?? 'http://127.0.0.1:3000'
const AUDIO_FIXTURE = fileURLToPath(new URL('./fixtures/gerclaw-health.wav', import.meta.url))
const DOCUMENT_FIXTURE = fileURLToPath(new URL('./fixtures/health-note.txt', import.meta.url))
const ENABLED = process.env.GERCLAW_REAL_E2E === '1'
const RAG_FAILURE_RECOVERY = process.env.GERCLAW_RAG_FAILURE_E2E === '1'
const RAG_FAILURE_FLAG = process.env.GERCLAW_RAG_FAILURE_FLAG
const TENANT_DATA_DIR = process.env.GERCLAW_DATA_DIR
  ?? join(process.cwd(), '.gerclaw', 'gateway-dsh', 'gerclaw-tenants')
const ARTIFACT_FORMATS = ['md', 'html', 'docx', 'pdf', 'png', 'jpg', 'json'] as const

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
    username: process.env.GERCLAW_TEST_DOCTOR_USERNAME ?? 'gc_doctor_test_20260823',
    password: required('GERCLAW_TEST_DOCTOR_PASSWORD'),
  },
  {
    label: '患者',
    username: process.env.GERCLAW_TEST_PATIENT_USERNAME ?? 'gc_patient_test_20260823',
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
    if (message.type() === 'error') {
      const source = message.location().url
      tripwire.consoleErrors.push(source ? `${message.text()} @ ${source}` : message.text())
    }
    if (message.type() === 'warning' && /agent-preset-not-found/u.test(message.text()))
      tripwire.consoleErrors.push(message.text())
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

const waitForWorkspace = async (page: Page, timeout = 60_000): Promise<void> => {
  await page.waitForURL(url => url.origin === BASE_URL && !url.pathname.startsWith('/auth/'), { timeout })
  await page.getByRole('button', { name: '开始语音输入' }).waitFor({ timeout })
  await page.locator('[data-composer-card] textarea').waitFor({ timeout })
}

const login = async (page: Page, identity: Identity): Promise<void> => {
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' })
  await page.getByLabel('用户名').fill(identity.username)
  await page.getByLabel('密码').fill(identity.password)
  await page.getByRole('button', { name: '进入健康工作台' }).click()
  await Promise.race([
    waitForWorkspace(page),
    page.getByText('用户名或密码不正确', { exact: true }).waitFor({ timeout: 60_000 })
      .then(() => { throw new Error(`${identity.label}测试账号凭据不匹配`) }),
  ])
  await expect.poll(() => page.locator('button[data-gerclaw-read-aloud]').count(), { timeout: 30_000 }).toBe(0)
}

const enterAsGuest = async (page: Page, timeout?: number): Promise<void> => {
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: /游客体验/u }).click()
  await waitForWorkspace(page, timeout)
  await expect.poll(() => page.locator('button[data-gerclaw-read-aloud]').count(), { timeout: 30_000 }).toBe(0)
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

const lastAssistantTurn = async (page: Page): Promise<string | null> =>
  page.locator('[data-turn-tail]').filter({ has: page.locator('button[data-gerclaw-read-aloud]') })
    .last().getAttribute('data-turn-tail').catch(() => null)

const visibleQuestion = async (page: Page): Promise<Locator | undefined> => {
  const questions = page.locator('[data-question-key]')
  for (let index = (await questions.count()) - 1; index >= 0; index -= 1) {
    const question = questions.nth(index)
    if (await question.isVisible().catch(() => false)) return question
  }
  return undefined
}

const visibleQuestionSignature = async (page: Page): Promise<string | null> => {
  const question = await visibleQuestion(page)
  if (question === undefined) return null
  return `${await question.getAttribute('data-question-key') ?? ''}:${await question.locator('h2').textContent() ?? ''}`
}

const answerVisibleQuestion = async (page: Page, text: string): Promise<boolean> => {
  const question = await visibleQuestion(page)
  if (question === undefined) return false
  const answers = question.getByRole('textbox')
  const count = await answers.count()
  for (let index = 0; index < count; index += 1) await answers.nth(index).fill(text)
  if (count > 0) {
    const action = question.getByRole('button', { name: /^(?:下一题|提交)$/u }).last()
    if (await action.count() > 0) await action.click()
    else await answers.last().press('Enter')
  }
  return count > 0
}

const waitForAssistantTurn = async (
  page: Page,
  before: string | null,
  timeout: number,
  answer?: string,
): Promise<void> => {
  await expect.poll(async () => {
    if (answer !== undefined) await answerVisibleQuestion(page, answer)
    return lastAssistantTurn(page)
  }, { timeout }).not.toBe(before)
}

const sendChat = async (page: Page, prompt: string, timeout = 180_000): Promise<void> => {
  const before = await lastAssistantTurn(page)
  await composer(page).fill(prompt)
  await composer(page).press('Enter')
  await waitForAssistantTurn(page, before, timeout)
}

const sendInteractiveChat = async (
  page: Page,
  prompt: string,
  timeout = 240_000,
): Promise<void> => {
  const before = await lastAssistantTurn(page)
  await composer(page).fill(prompt)
  await composer(page).press('Enter')
  await waitForAssistantTurn(
    page,
    before,
    timeout,
    '请根据我已经提供的信息继续，必要时给出可填写的示例。',
  )
}

const closeDialog = async (dialog: Locator): Promise<void> => {
  await dialog.getByRole('button', { name: '关闭' }).click()
  await expect.poll(() => dialog.count()).toBe(0)
}

const expectTaskResult = async (dialog: Locator, timeout = 180_000): Promise<void> => {
  const final = dialog.locator('[data-gerclaw-final]')
  const error = dialog.getByRole('alert')
  await Promise.race([
    final.waitFor({ timeout }),
    error.waitFor({ timeout }).then(async () => {
      throw new Error(`健康任务失败：${await error.innerText()}`)
    }),
  ])
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
  await page.getByRole('button', { name: '更多', exact: true }).click()
  const more = page.getByRole('dialog', { name: '更多健康服务' })
  await more.getByRole('button', { name: new RegExp(name, 'u') }).click()
  return page.getByRole('dialog')
}

const runRag = async (page: Page, options: {
  file?: Parameters<Locator['setInputFiles']>[0]
  query: string
  expectedText?: string
  forbiddenText?: string
  requireSourceLinks?: boolean
}): Promise<Locator> => {
  const dialog = await openMore(page, '文档库')
  if (options.file !== undefined) {
    await dialog.getByLabel('添加到我的文档库').setInputFiles(options.file)
    await containsText(dialog.getByRole('status'), '已加入', 60_000)
  }
  await dialog.getByLabel('检索词').fill(options.query)
  await dialog.getByRole('button', { name: '检索本地与医学资料' }).click()
  await expectTaskResult(dialog, 240_000)
  const result = dialog.locator('[data-gerclaw-final]')
  if (options.expectedText !== undefined) await containsText(result, options.expectedText)
  if (options.forbiddenText !== undefined)
    expect(await result.innerText()).not.toContain(options.forbiddenText)
  if (options.requireSourceLinks !== false)
    expect(await result.getByRole('link', { name: '打开原文' }).count()).toBeGreaterThanOrEqual(3)
  return dialog
}

type BrowserArtifact = {
  artifactId: string
  taskId: string
  name: string
  format: string
  mediaType: string
  size: number
}

const allArtifacts = async (page: Page): Promise<BrowserArtifact[]> => page.evaluate(async () => {
  const response = await fetch('/gerclaw/api/bootstrap')
  if (!response.ok) throw new Error('无法读取账号产物')
  const body = await response.json() as { artifacts?: BrowserArtifact[] }
  return body.artifacts ?? []
})

type WebSocketProbe = {
  closed: boolean
  receivedMessage: boolean
  closeCode: number | null
  closeReason: string
  timedOut: boolean
}

const probeWebSocket = async (page: Page, sessionId: string): Promise<WebSocketProbe> => page.evaluate(
  sessionId => new Promise<WebSocketProbe>((resolve) => {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(`${protocol}//${location.host}/gerclaw/api/voice/asr-stream?sessionId=${encodeURIComponent(sessionId)}`)
    let receivedMessage = false
    let timedOut = false
    let settled = false
    let timeoutFallback: ReturnType<typeof setTimeout> | undefined
    const finish = (closed: boolean, closeCode: number | null, closeReason: string): void => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      if (timeoutFallback !== undefined) clearTimeout(timeoutFallback)
      resolve({ closed, receivedMessage, closeCode, closeReason, timedOut })
    }
    const timer = setTimeout(() => {
      timedOut = true
      try { socket.close(4000, 'test-timeout') } catch { finish(false, null, 'test-timeout'); return }
      timeoutFallback = setTimeout(() => { finish(false, null, 'test-timeout') }, 1_000)
    }, 5_000)
    socket.addEventListener('message', () => {
      receivedMessage = true
      try { socket.close(4001, 'unexpected-message') } catch { finish(false, null, 'unexpected-message') }
    })
    socket.addEventListener('close', (event) => { finish(true, event.code, event.reason) })
  }),
  sessionId,
)

const runSevenArtifacts = async (page: Page): Promise<BrowserArtifact[]> => {
  const before = new Set((await allArtifacts(page)).map(item => item.artifactId))
  await page.getByRole('button', { name: '综合量表' }).click()
  const dialog = page.getByRole('dialog', { name: '综合量表' })
  await dialog.getByLabel('选择量表').selectOption('phq9')
  await dialog.getByRole('button', { name: '完成确定性计分' }).click()
  await expectTaskResult(dialog)
  await dialog.getByRole('button', { name: '导出七种格式' }).click()
  await containsText(
    dialog.getByRole('status').filter({ hasText: '已生成 7 个格式' }),
    '已生成 7 个格式',
    120_000,
  )
  await expect.poll(async () => (await allArtifacts(page)).filter(
    item => !before.has(item.artifactId),
  ), { timeout: 30_000 }).toHaveLength(7)
  const created = (await allArtifacts(page)).filter(item => !before.has(item.artifactId))
  expect([...new Set(created.map(item => item.format))].sort()).toEqual([...ARTIFACT_FORMATS].sort())
  expect(new Set(created.map(item => item.taskId)).size).toBe(1)
  const downloads = await page.evaluate(async artifacts => Promise.all(artifacts.map(async (artifact) => {
    const response = await fetch(`/gerclaw/api/artifacts/${encodeURIComponent(artifact.artifactId)}`)
    return {
      status: response.status,
      mediaType: response.headers.get('content-type'),
      disposition: response.headers.get('content-disposition'),
      size: (await response.arrayBuffer()).byteLength,
    }
  })), created)
  for (const [index, download] of downloads.entries()) {
    expect(download.status).toBe(200)
    expect(download.mediaType).toBe(created[index]!.mediaType)
    expect(download.disposition).toContain('attachment')
    expect(download.size).toBe(created[index]!.size)
  }
  await closeDialog(dialog)
  const layout = page.locator('[data-gerclaw-artifact-layout]')
  await expect.poll(() => layout.locator('li').count(), { timeout: 30_000 }).toBeGreaterThanOrEqual(7)
  await layout.locator('li button').filter({ hasText: /\.png/iu }).first().click()
  await visible(layout.locator('[data-gerclaw-artifact-preview] img'))
  await layout.locator('li button').filter({ hasText: /\.pdf/iu }).first().click()
  await visible(layout.locator('[data-gerclaw-artifact-preview] iframe'))
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    layout.locator('[data-gerclaw-artifact-preview] a').click(),
  ])
  expect(download.suggestedFilename()).toMatch(/\.pdf$/u)
  return created
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

  dialog = await runRag(page, { file: DOCUMENT_FIXTURE, query: '阿司匹林用药安全' })
  const sourceLinks = await dialog.getByRole('link', { name: '打开原文' }).all()
  expect(sourceLinks.length).toBeGreaterThanOrEqual(3)
  const hrefs = await Promise.all(sourceLinks.map(link => link.getAttribute('href')))
  expect(hrefs.some(href => href?.includes('pubmed.ncbi.nlm.nih.gov'))).toBe(true)
  expect(hrefs.some(href => href?.includes('fda.gov'))).toBe(true)
  expect(hrefs.some(href => href?.includes('medlineplus.gov'))).toBe(true)
  await dialog.getByRole('button', { name: '导出七种格式' }).click()
  await containsText(
    dialog.getByRole('status').filter({ hasText: '已生成 7 个格式' }),
    '已生成 7 个格式',
    120_000,
  )
  await closeDialog(dialog)

  await expect.poll(() => page.locator('[data-gerclaw-artifact-layout] li').count(), { timeout: 30_000 }).toBeGreaterThanOrEqual(7)
  await hasAttribute(page.locator('[data-gerclaw-artifact-preview] a'), 'href', /\/gerclaw\/api\/artifacts\//u)
}

const runVoice = async (page: Page): Promise<void> => {
  const turnBeforeRecording = await lastAssistantTurn(page)
  const mic = page.getByRole('button', { name: '开始语音输入' })
  await mic.click()
  const stop = page.getByRole('button', { name: '停止录音并发送' })
  await visible(stop)
  await visible(page.getByRole('status').filter({ hasText: /正在识别/u }), 60_000)
  // Chromium loops the fake microphone fixture after EOF. Stop as soon as the
  // complete first utterance reaches the native composer so the next loop
  // cannot append a duplicate prefix to Qianwen's final transcript.
  await expect.poll(
    () => composer(page).inputValue(),
    { timeout: 30_000 },
  ).toContain('正在服用阿司匹林')
  await stop.click()
  await visible(page.getByRole('status').filter({ hasText: /已完成转写/u }), 120_000)
  const transcript = /最近晚上睡不好.*正在服用阿司匹林/u
  await visible(page.getByText(transcript).last(), 120_000)
  await waitForAssistantTurn(
    page,
    turnBeforeRecording,
    360_000,
    '暂不补充更多个人资料，请直接给出简短的健康回应。',
  )
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

  const transcriptCount = await page.getByText(transcript).count()
  const turnBeforeUpload = await lastAssistantTurn(page)
  await page.locator('[data-gerclaw-composer-document] input[type="file"]').setInputFiles(AUDIO_FIXTURE)
  await visible(page.getByRole('status').filter({ hasText: /正在(?:解码|连接|识别)音频/u }), 30_000)
  await visible(page.getByRole('status').filter({ hasText: /已完成转写/u }), 120_000)
  await expect.poll(
    () => page.getByText(transcript).count(),
    { timeout: 120_000 },
  ).toBeGreaterThan(transcriptCount)
  await waitForAssistantTurn(
    page,
    turnBeforeUpload,
    360_000,
    '暂不补充更多个人资料，请直接给出简短的健康回应。',
  )

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

  const before = await lastAssistantTurn(page)
  await composer(page).fill('/plan 为未来三天制定一个不超过三步的健康记录计划，并提交审核。')
  await composer(page).press('Enter')
  const review = page.locator('[data-plan-review-key]')
  const planDeadline = Date.now() + 180_000
  while (Date.now() < planDeadline && !(await review.isVisible().catch(() => false))) {
    await answerVisibleQuestion(page, '无需补充个人资料，请按通用健康记录方案继续提交计划审核。')
    await page.waitForTimeout(250)
  }
  await review.waitFor({ timeout: 1_000 })
  await visible(review.getByRole('button', { name: /确认执行/u }))
  await review.getByRole('button', { name: /确认执行/u }).click()
  await waitForAssistantTurn(
    page,
    before,
    360_000,
    '无需补充个人资料，请按通用健康记录方案继续。',
  )

  const goal = page.locator('[data-goal-bar]')
  if (await goal.isVisible().catch(() => false)) {
    await composer(page).fill('/goal clear')
    await composer(page).press('Enter')
    await expect.poll(() => goal.count(), { timeout: 30_000 }).toBe(0)
  }
  await composer(page).fill('/goal 建立一个持续记录血压的健康目标')
  await composer(page).press('Enter')
  await goal.waitFor({ timeout: 30_000 })
  await containsText(goal, /记录血压/u)
  await goal.getByRole('button', { name: /暂停/u }).click()
  await visible(goal.getByRole('button', { name: /恢复/u }))
  await composer(page).fill('/goal edit 持续记录早晚血压并观察趋势')
  await composer(page).press('Enter')
  await containsText(goal, /早晚血压/u)
  await goal.getByRole('button', { name: /恢复/u }).click()
  await visible(goal.getByRole('button', { name: /暂停/u }))
  await goal.getByRole('button', { name: /暂停/u }).click()
  await visible(goal.getByRole('button', { name: /恢复/u }))
  await composer(page).fill('/goal clear')
  await composer(page).press('Enter')
  await expect.poll(() => goal.count(), { timeout: 30_000 }).toBe(0)
}

const runPrescription = async (page: Page): Promise<void> => {
  const tasks = page.locator('[data-gerclaw-conversation-task]')
  const beforeTaskId = await tasks.last().getAttribute('data-gerclaw-task-id').catch(() => null)
  const hasNewTask = async (): Promise<boolean> => {
    const taskId = await tasks.last().getAttribute('data-gerclaw-task-id').catch(() => null)
    return taskId !== null && taskId !== beforeTaskId
  }
  let turn = await lastAssistantTurn(page)
  await page.getByRole('button', { name: '五大处方', exact: true }).click()
  await expect.poll(async () =>
    await hasNewTask()
    || await lastAssistantTurn(page) !== turn
    || await visibleQuestionSignature(page) !== null,
  { timeout: 600_000 }).toBe(true)
  for (const answer of [
    '我的健康目标是改善睡眠。',
    '我最近夜间易醒，正在服用阿司匹林每日一次，没有已知药物过敏。',
    '没有其他需要补充的个人资料，请根据已经提供的信息继续。',
  ]) {
    if (await hasNewTask()) break
    const questionSignature = await visibleQuestionSignature(page)
    turn = await lastAssistantTurn(page)
    await expect.poll(async () => {
      if (await hasNewTask()) return 'done'
      if (await answerVisibleQuestion(page, answer)) return 'submitted'
      const send = page.getByRole('button', { name: '发送消息' })
      if (await composer(page).isEditable().catch(() => false)) {
        await composer(page).fill(answer)
        if (await send.isEnabled().catch(() => false)) {
          await send.click()
          return 'submitted'
        }
      }
      return 'waiting'
    }, { timeout: 600_000 }).not.toBe('waiting')
    if (await hasNewTask()) break
    await expect.poll(async () =>
      await hasNewTask()
      || await lastAssistantTurn(page) !== turn
      || (questionSignature !== null
        && await visibleQuestionSignature(page) !== questionSignature),
    { timeout: 600_000 }).toBe(true)
  }
  await expect.poll(hasNewTask, { timeout: 240_000 }).toBe(true)
  const card = tasks.last()
  for (const chapter of ['药物处方', '运动处方', '营养处方', '心理处方', '康复处方'])
    await visible(card.getByText(chapter, { exact: true }).first())
  expect(await page.getByText(/独立处方表单/u).count()).toBe(0)
}

const assertProductBaseline = async (page: Page): Promise<void> => {
  const sidebarToggle = page.getByRole('button', { name: /^(?:打开|展开)侧边栏$/u }).first()
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
  for (const name of ['五大处方', '综合量表', '用药核对', '健康档案', '更多', '设置']) {
    const button = page.getByRole('button', { name })
    await hasAttribute(button, 'aria-label', name)
  }
  expect(await page.getByRole('button', { name: '健康对话', exact: true }).count()).toBe(0)
  expect(await page.locator('body').innerText()).not.toMatch(/工作区|选择工作区|添加工作区/u)
  if (sidebarWasCollapsed) {
    await page.getByRole('button', { name: '收起侧边栏' }).click()
    await visible(composer(page))
  }
}

const runProductShellMatrix = async (page: Page): Promise<void> => {
  await assertProductBaseline(page)
  await sendChat(page, '请用二级标题、加粗文字和三项列表回答：老年人今天如何安全记录血压？')
  expect(await page.locator('pre').filter({ hasText: /老年人今天/u }).count()).toBe(0)
  await runPlanGoalAndSkills(page)
}

const runIdentityMatrix = async (page: Page): Promise<void> => {
  await runProductShellMatrix(page)
  await runVoice(page)
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

  for (const identity of ['doctor', 'patient'] as const) {
    it(`阶段一：${identity === 'doctor' ? '医生' : '患者'}产品壳层与主对话`, async () => {
      const selected = identities()[identity === 'doctor' ? 0 : 1]!
      const context = await browser.newContext({ locale: 'zh-CN', viewport: { width: 1440, height: 960 } })
      contexts.push(context)
      const page = await context.newPage()
      const tripwire = watch(page)
      await login(page, selected)
      await runProductShellMatrix(page)
      assertClean(tripwire)
      await logout(page)
    }, 1_200_000)
  }

  for (const identity of ['doctor', 'patient', 'guest'] as const) {
    it(`阶段二：${identity === 'doctor' ? '医生' : identity === 'patient' ? '患者' : '游客'}语音与五大处方`, async () => {
      const context = await browser.newContext({ locale: 'zh-CN', permissions: ['microphone'], viewport: { width: 1440, height: 960 } })
      contexts.push(context)
      const page = await context.newPage()
      const tripwire = watch(page)
      if (identity === 'guest') await enterAsGuest(page)
      else await login(page, identities()[identity === 'doctor' ? 0 : 1]!)
      await runVoice(page)
      await runPrescription(page)
      assertClean(tripwire)
      await logout(page)
    }, 1_500_000)
  }

  for (const identity of ['doctor', 'patient', 'guest'] as const) {
    it(`阶段三：${identity === 'doctor' ? '医生' : identity === 'patient' ? '患者' : '游客'}共享与私有医学资料`, async () => {
      const context = await browser.newContext({ locale: 'zh-CN', viewport: { width: 1440, height: 960 } })
      contexts.push(context)
      const page = await context.newPage()
      const tripwire = watch(page)
      if (identity === 'guest') await enterAsGuest(page)
      else await login(page, identities()[identity === 'doctor' ? 0 : 1]!)
      const dialog = await runRag(page, { file: DOCUMENT_FIXTURE, query: '阿司匹林用药安全' })
      await closeDialog(dialog)
      assertClean(tripwire)
      await logout(page)
    }, 600_000)
  }

  it('阶段三：医生私有资料不可被患者检索', async () => {
    const doctor = identities()[0]!
    const patient = identities()[1]!
    const doctorContext = await browser.newContext({ locale: 'zh-CN', viewport: { width: 1280, height: 900 } })
    const patientContext = await browser.newContext({ locale: 'zh-CN', viewport: { width: 1280, height: 900 } })
    contexts.push(doctorContext, patientContext)
    const doctorPage = await doctorContext.newPage()
    const patientPage = await patientContext.newPage()
    const doctorTripwire = watch(doctorPage)
    const patientTripwire = watch(patientPage)
    await login(doctorPage, doctor)
    await login(patientPage, patient)
    const marker = `GC_STAGE3_PRIVATE_${Date.now()}`
    const doctorDialog = await runRag(doctorPage, {
      file: {
        name: 'doctor-private.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from(`${marker}，晨起血压 138/82 毫米汞柱。`),
      },
      query: marker,
      expectedText: marker,
      requireSourceLinks: false,
    })
    await closeDialog(doctorDialog)
    const patientDialog = await runRag(patientPage, {
      query: marker,
      forbiddenText: marker,
      requireSourceLinks: false,
    })
    await closeDialog(patientDialog)
    assertClean(doctorTripwire)
    assertClean(patientTripwire)
    await logout(doctorPage)
    await logout(patientPage)
  }, 600_000)

  it.skipIf(!RAG_FAILURE_RECOVERY)('阶段三：医学资料服务失败时明确提示且不伪造结果', async () => {
    const context = await browser.newContext({ locale: 'zh-CN', viewport: { width: 1280, height: 900 } })
    contexts.push(context)
    const page = await context.newPage()
    await enterAsGuest(page)
    if (!RAG_FAILURE_FLAG) throw new Error('缺少医学资料服务失败标记路径')
    await writeFile(RAG_FAILURE_FLAG, 'fail')
    const dialog = await openMore(page, '文档库')
    await dialog.getByLabel('检索词').fill('阿司匹林用药安全')
    await dialog.getByRole('button', { name: '检索本地与医学资料' }).click()
    const alert = dialog.getByRole('alert')
    await containsText(alert, '医学资料服务暂时不可用，请稍后重试', 120_000)
    expect(await dialog.locator('[data-gerclaw-final]').count()).toBe(0)
    expect(await alert.innerText()).not.toMatch(/ECONN|127\.0\.0\.1|fetch failed|SiliconFlow/iu)
    await closeDialog(dialog)
    await logout(page)
  }, 300_000)

  for (const identity of ['doctor', 'patient'] as const) {
    it(`阶段四：${identity === 'doctor' ? '医生' : '患者'}七种产物、下载与历史恢复`, async () => {
      const selected = identities()[identity === 'doctor' ? 0 : 1]!
      const context = await browser.newContext({ locale: 'zh-CN', viewport: { width: 1280, height: 900 } })
      contexts.push(context)
      const page = await context.newPage()
      const tripwire = watch(page)
      await login(page, selected)
      const created = await runSevenArtifacts(page)
      assertClean(tripwire)
      await logout(page)
      await login(page, selected)
      const restored = new Set((await allArtifacts(page)).map(item => item.artifactId))
      for (const artifact of created) expect(restored.has(artifact.artifactId)).toBe(true)
      assertClean(tripwire)
      await logout(page)
    }, 600_000)
  }

  it('阶段四：游客七种产物并在退出后清理专用目录', async () => {
    const guestsRoot = join(TENANT_DATA_DIR, 'guests')
    const before = (await readdir(guestsRoot)).sort()
    const context = await browser.newContext({ locale: 'zh-CN', viewport: { width: 1280, height: 900 } })
    contexts.push(context)
    const page = await context.newPage()
    const tripwire = watch(page)
    await enterAsGuest(page)
    await runSevenArtifacts(page)
    expect((await readdir(guestsRoot)).length).toBe(before.length + 1)
    assertClean(tripwire)
    await logout(page)
    await expect.poll(async () => (await readdir(guestsRoot)).sort(), { timeout: 30_000 }).toEqual(before)
  }, 600_000)

  for (const identity of ['doctor', 'patient'] as const) {
    it(`${identity === 'doctor' ? '医生' : '患者'}账号完整真实路径`, async () => {
      const selected = identities()[identity === 'doctor' ? 0 : 1]!
      const context = await browser.newContext({ locale: 'zh-CN', permissions: ['microphone'], viewport: { width: 1440, height: 960 } })
      contexts.push(context)
      const page = await context.newPage()
      const tripwire = watch(page)
      onTestFailed(async () => { await page.screenshot({ path: `output/playwright/gerclaw-${identity}-failed.png`, fullPage: true }) })
      await login(page, selected)
      await runIdentityMatrix(page)
      assertClean(tripwire)
      await logout(page)
    }, 2_400_000)
  }

  it('游客完整真实路径并在退出后清理', async () => {
    const context = await browser.newContext({ locale: 'zh-CN', permissions: ['microphone'], viewport: { width: 1280, height: 900 } })
    contexts.push(context)
    const page = await context.newPage()
    const tripwire = watch(page)
    onTestFailed(async () => { await page.screenshot({ path: 'output/playwright/gerclaw-guest-failed.png', fullPage: true }) })
    await enterAsGuest(page)
    await runIdentityMatrix(page)
    assertClean(tripwire)
    await logout(page)
  }, 2_400_000)

  it('阶段四：拒绝跨账号会话、文件、产物、下载与 WebSocket 标识', async () => {
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
    const foreignIds = [ids.artifact, ids.document, ids.task, ids.session]
      .filter((value): value is string => typeof value === 'string')
    const patientBootstrap = await patientPage.evaluate(async () => {
      const response = await fetch('/gerclaw/api/bootstrap')
      return { status: response.status, body: await response.text() }
    })
    expect(patientBootstrap.status).toBe(200)
    for (const foreignId of foreignIds) expect(patientBootstrap.body).not.toContain(foreignId)
    const missingId = `missing-${Date.now()}`
    for (const [foreignPath, missingPath] of [
      [`/gerclaw/api/artifacts/${ids.artifact}`, `/gerclaw/api/artifacts/${missingId}`],
      [`/gerclaw/api/documents/${ids.document}`, `/gerclaw/api/documents/${missingId}`],
    ] as Array<[string, string]>) {
      const { foreign, missing } = await patientPage.evaluate(async ([foreignPath, missingPath]: [string, string]) => {
        const read = async (path: string) => {
          const response = await fetch(path)
          return { status: response.status, body: await response.text() }
        }
        return { foreign: await read(foreignPath), missing: await read(missingPath) }
      }, [foreignPath, missingPath] as [string, string])
      expect(foreign).toEqual(missing)
      expect(foreign.status).toBe(400)
    }
    const bootstrap = await patientPage.evaluate(async (sessionId) => {
      const response = await fetch('/gerclaw/api/bootstrap', { headers: { 'x-gerclaw-session-id': String(sessionId) } })
      return { status: response.status, body: await response.text() }
    }, ids.session)
    expect(bootstrap.status).toBe(400)
    for (const foreignId of foreignIds) expect(bootstrap.body).not.toContain(foreignId)
    const missingSession = `missing-session-${Date.now()}`
    const missingBootstrap = await patientPage.evaluate(async (sessionId) => {
      const response = await fetch('/gerclaw/api/bootstrap', { headers: { 'x-gerclaw-session-id': sessionId } })
      return { status: response.status, body: await response.text() }
    }, missingSession)
    expect(bootstrap).toEqual(missingBootstrap)
    const wsResult = await probeWebSocket(patientPage, ids.session!)
    const missingWsResult = await probeWebSocket(patientPage, missingSession)
    expect(wsResult).toEqual(missingWsResult)
    expect(wsResult.timedOut).toBe(false)
    expect(wsResult.closed).toBe(true)
    expect(wsResult.receivedMessage).toBe(false)
    expect(wsResult.closeCode).not.toBe(4000)
    expect(wsResult.closeReason).not.toBe('test-timeout')
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
      const prescription = page.getByRole('button', { name: '五大处方' })
      await prescription.focus()
      expect(await prescription.evaluate(element => element === document.activeElement)).toBe(true)
      await prescription.hover()
      await visible(page.getByText('五大处方', { exact: true }).first())
      await logout(page)
    })
  }
})
