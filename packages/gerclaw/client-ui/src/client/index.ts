import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'
import { createElement } from 'react'
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import type {} from '@deepseek-ai/dsh-client-ui-layout/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type {} from '@deepseek-ai/dsh-client-ui-theme/client'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type {} from 'dsh-better-sidebar/client'
import gerclawAppRemote from '@gerclaw/app/remote'
import type { ArtifactDescriptor, GerclawJsonValue, MedicalTaskKind } from '@gerclaw/app/types'
import { ArtifactsTab } from './ArtifactsTab.tsx'
import { GerclawBrandMark, GerclawBrandName } from './Brand.tsx'
import { ConversationDocumentUpload } from './ConversationDocumentUpload.tsx'
import { FriendlySettings } from './FriendlySettings.tsx'
import { MedicalNavigation, type MedicalNavigationInjected } from './MedicalNavigation.tsx'
import type { MedicalRemoteActions } from './MedicalFeature.tsx'
import { MedicalTaskCard } from './MedicalTaskCard.tsx'
import { medicalTaskDefinition } from './medical-task-definition.ts'
import { QuickPrompts } from './QuickPrompts.tsx'
import { installProductStyles } from './styles.ts'

export const inject = ['slots', 'theme', 'layout', 'betterSidebar', 'sessions', 'workspaces', 'conversation', 'conversationEvents', 'remote']

declare module '@deepseek-ai/cordis' {
  interface Events {
    /** A GerClaw export completed in this browser client. */
    'gerclaw/artifacts-created'(sessionId: SessionId): void
  }
}

const INTERNAL_PLATFORM_NAME = ['DeepSeek', 'Harness'].join(' ')

function removeInternalBrand(value: string): string {
  return value.replaceAll(INTERNAL_PLATFORM_NAME, 'GerClaw').replace(/\bDSH\b/giu, 'GerClaw')
}

export async function apply(ctx: ClientContext): Promise<void> {
  const disposeRemote = await ctx.remote.$mount(gerclawAppRemote)
  ctx.effect(() => async () => { await disposeRemote() }, 'gerclaw client: medical remote')
  const medicalRemote: MedicalRemoteActions = {
    submit: async (
      kind: MedicalTaskKind,
      sessionId: string,
      input: GerclawJsonValue,
      requestId: string,
      signal: AbortSignal,
    ) => {
      const result = await ctx.remote.gerclawApp.submit(sessionId as SessionId, { requestId, kind, input }, signal)
      if (!result.ok) throw new Error(result.error.message)
      return result.value
    },
    cancel: async (sessionId: string, requestId: string): Promise<boolean> => {
      const result = await ctx.remote.gerclawApp.cancel(sessionId as SessionId, { requestId })
      if (!result.ok) throw new Error(result.error.message)
      return result.value.cancelled
    },
    export: async (
      sessionId: string,
      taskId: string,
      formats: ArtifactDescriptor['format'][],
    ): Promise<ArtifactDescriptor[]> => {
      const result = await ctx.remote.gerclawApp.export(sessionId as SessionId, { taskId, formats })
      if (!result.ok) throw new Error(result.error.message)
      ctx.emit('gerclaw/artifacts-created', sessionId as SessionId)
      return result.value.artifacts
    },
  }
  ctx.conversationEvents.register(medicalTaskDefinition)
  installProductStyles(ctx)
  if (typeof document !== 'undefined') {
    const prior = document.title
    const copy = (): void => {
      const title = 'GerClaw｜老年慢病智慧诊疗助手'
      if (document.title !== title) document.title = title
      for (const element of document.querySelectorAll<HTMLElement>('[data-phase="hero"] *')) {
        if (element.children.length !== 0) continue
        if (element.textContent === '探索未至之境') element.textContent = '安心管理每一天'
        if (element.textContent === '预览版' && !element.hidden) element.hidden = true
      }
      const productTerms: Record<string, string> = {
        '命令': '能力',
        'plan': '计划模式',
        'Enter or leave plan mode': '先制定步骤，经确认后再执行',
        'goal': '设定目标',
        'set or view the goal for a long-running task': '设置、查看或继续健康目标',
        'library': '本地知识库',
        'Local knowledge base: list libraries, count chunks, and check index health': '查看本账号医学资料库与索引状态',
        'followup': '随访问卷',
        'followup-questionnaire': '随访问卷',
        'risk-assessment': '风险评估',
        'health-education': '健康教育',
        'medication-reminder': '用药提醒',
        'model': '选择模型',
        'Select model for this session': '选择本次对话使用的模型',
        'Think': '分析过程',
        'Search': '联网查找',
        'Fetch': '读取来源',
        'Glob': '查找本账号文件',
        'Grep': '查找相关健康信息',
        'Read': '阅读本账号文件',
        'Write': '保存文件',
        'Edit': '更新健康记录',
        'record_chronic_measurement': '保存慢病测量',
        'Deep diving...': '正在深入分析…',
        'Tool call': '查阅健康资料',
        'Skill': '加载健康能力',
        '去聊天里说': '继续讨论',
      }
      for (const element of document.querySelectorAll<HTMLElement>('body *')) {
        if (element.children.length !== 0) continue
        const original = element.textContent.trim()
        const expectedPlanDiscussion = 'The user dismissed the plan review to speak instead'
        const expectedPlanRevision = 'The user chose to keep planning'
        if (original === '失败') {
          const failedTool = element.closest<HTMLElement>('[data-tool]')?.dataset.tool
          if (failedTool === 'ask_user_question') {
            element.textContent = '提问已中断，可恢复目标后继续'
            continue
          }
          let parent: HTMLElement | null = element.parentElement
          for (let level = 0; level < 6 && parent; level++, parent = parent.parentElement) {
            const text = parent.textContent
            if (text.includes(expectedPlanDiscussion)) {
              element.textContent = '继续讨论'
              break
            }
            if (text.includes(expectedPlanRevision)) {
              element.textContent = '继续规划'
              break
            }
          }
        }
        if (original.includes(expectedPlanDiscussion)) {
          element.textContent = '用户选择回到对话继续修改计划，当前计划尚未执行。'
          continue
        }
        if (original.includes(expectedPlanRevision)) {
          element.textContent = '用户选择继续规划，请根据意见修订后再次提交审核。'
          continue
        }
        if (original.includes('因为您选择了语音输入，计划未能进入审批流程')) {
          element.textContent = '您选择继续讨论，因此计划尚未执行。'
          continue
        }
        if (original.includes('The tool call was interrupted after it was recorded')) {
          element.textContent = '计划审批因服务重启而中断，请重新提交计划。'
          continue
        }
        if (/^The user has provided:?$/iu.test(original)) {
          element.textContent = '正在整理您刚刚补充的健康资料。'
          continue
        }
        if (original.startsWith('目标 ID：')) {
          element.textContent = '已定位当前健康目标。'
          continue
        }
        if (original.startsWith('阶段已从 active')) {
          element.textContent = '目标状态已更新为完成。'
          continue
        }
        if (original.startsWith('调用 get_goal')) {
          element.textContent = '已确认目标管理能力可用。'
          continue
        }
        if (original.startsWith('调用 update_goal')) {
          element.textContent = '已将当前健康目标标记为完成。'
          continue
        }
        if (original === 'ID') {
          element.textContent = '当前目标'
          continue
        }
        if (original === '修订' || original === '修订版本') {
          element.textContent = '状态记录'
          continue
        }
        if (original === '阶段') {
          element.textContent = '当前状态'
          continue
        }
        if (original === '激活状态') {
          element.textContent = '运行状态'
          continue
        }
        if (original === '最大轮次' || original === '最大轮次限制') {
          const row = element.closest<HTMLElement>('li') ?? element.parentElement
          if (row) row.hidden = true
          continue
        }
        if (/^:\s*active(?:（已激活）)?$/u.test(original)) {
          element.textContent = '：进行中'
          continue
        }
        if (/^:\s*complete(?:（已完成）)?$/u.test(original)) {
          element.textContent = '：已完成'
          continue
        }
        if (/^:\s*disarmed(?:（已解除武装）)?$/u.test(original)) {
          element.textContent = '：已结束'
          continue
        }
        if (original.startsWith('exit_plan_mode ·')) {
          element.textContent = '已提交计划供审核'
          continue
        }
        if (original === 'Plan mode on. Use /plan off to leave.') {
          element.textContent = '计划模式已开启，可随时关闭。'
          continue
        }
        if (/^Goal (?:created|updated|paused|resumed)\b/u.test(original)) {
          const objective = /Objective:\s*([\s\S]*?)\s+Rounds:/u.exec(original)?.[1]?.trim()
          const prefix = original.startsWith('Goal created')
            ? '目标已创建'
            : original.startsWith('Goal updated')
              ? '目标已更新'
              : original.startsWith('Goal paused')
                ? '目标已暂停'
                : '目标已恢复'
          element.textContent = objective ? `${prefix}：${objective}` : prefix
          continue
        }
        if (original === 'Goal cleared.') {
          element.textContent = '目标已清除。'
          continue
        }
        if (original.startsWith('library_search ·')) {
          element.textContent = '已核对本地医学资料'
          continue
        }
        if (original.startsWith('library_list ·')) {
          element.textContent = '已查看本账号资料库'
          continue
        }
        if (original.startsWith('mcp__memorix__')) {
          element.textContent = '已查看当前账号的健康记忆'
          continue
        }
        if (original.startsWith('record_chronic_measurement ·')) {
          element.textContent = '保存慢病测量'
          continue
        }
        let cleaned = removeInternalBrand(original)
          .replace(/~\/[^\s'"`]*packages\/gerclaw\/skills\/skills\/[^\s'"`]+\/SKILL\.md/giu, 'GerClaw 内置能力说明')
          .replace(/record_chronic_measurement/gu, '慢病测量保存能力')
          .replace(/\bgoal-[a-z0-9-]{16,}\b/giu, '当前健康目标')
          .replace(/\bget_goal\b/gu, '查看目标')
          .replace(/\b(?:update_goal|create_goal)\b/gu, '更新目标')
          .replace(/查看目标\s*·\s*\{[^}]*\}/gu, '已查看目标进度')
          .replace(/更新目标\s*·\s*[a-z_-]+/giu, '已更新目标状态')
          .replace(/更新目标\s*\([^)]*\)/gu, '更新目标')
          .replace(/\.gerclaw-rag\/[a-f0-9]{16,64}\.md/giu, '本地医学参考资料')
          .replace(/\b[a-f0-9]{16,64}\b/giu, '本地资料')
          .replace(/gerclaw-(?:medical-sf-v2|med-knowledge)/giu, '本地医学资料库')
          .replace(
            /\/(?:Users|home)\/[^\s'"`]+\/(?:data\/workspace\/)?([^\s'"`/]+(?:\.[\p{L}\p{N}_-]+)?)/giu,
            '当前账号工作区/$1',
          )
        const toolView = element.closest<HTMLElement>('[data-tool]')
        const toolButton = element.closest<HTMLButtonElement>('button')
        const toolText = toolView?.textContent ?? toolButton?.textContent ?? ''
        const toolName = toolView?.dataset.tool
        if (
          toolText.includes('Glob')
          || toolText.includes('查找本账号文件')
        ) {
          if (/[?*{}[\]]/u.test(cleaned) || cleaned.startsWith('**/'))
            cleaned = '正在查找相关健康记录'
        }
        if (
          toolText.includes('Search')
          || toolText.includes('联网查找')
        ) {
          if (cleaned !== 'Search' && cleaned !== '联网查找')
            cleaned = '正在核对权威来源'
        }
        if (
          toolView !== null
          && toolName !== undefined
          && cleaned.startsWith(`${toolName} ·`)
        ) {
          cleaned = toolName === 'get_goal'
            ? '已查看目标进度'
            : toolName === 'update_goal' || toolName === 'create_goal'
              ? '已更新目标状态'
              : toolName === 'ask_user_question'
                ? '正在确认所需信息'
                : toolName.startsWith('mcp__')
                  ? '已核对当前账号的健康资料'
                  : '已完成此步骤'
        }
        if (cleaned !== original) element.textContent = cleaned
        if (element.textContent.trim() === 'Think') {
          const row = element.closest<HTMLElement>('[data-disclosure-row]')
          if (row?.parentElement) row.parentElement.hidden = false
        }
        const translated = productTerms[element.textContent.trim()]
        if (translated) element.textContent = translated
        if (element.textContent.trim() === '查阅健康资料') {
          let parent: HTMLElement | null = element.parentElement
          for (let level = 0; level < 6 && parent; level++, parent = parent.parentElement) {
            const text = parent.textContent
            if (
              text.includes('用户选择回到对话继续修改计划')
              || text.includes('用户选择继续规划')
              || text.includes('已提交计划供审核')
            ) {
              element.textContent = '计划审核'
              break
            }
          }
        }
      }
      for (const textarea of document.querySelectorAll<HTMLTextAreaElement>('textarea')) {
        if (textarea.placeholder === '描述你想要构建的内容')
          textarea.placeholder = '请描述最想解决的健康问题'
      }
      for (const button of document.querySelectorAll<HTMLButtonElement>('button')) {
        const label = button.getAttribute('aria-label') ?? button.textContent.trim()
        if (label === '命令') {
          button.setAttribute('aria-label', '能力')
          button.title = '能力：选择健康技能、计划模式或目标'
        }
        if (label === 'Session log' || label.startsWith('上下文已用')) button.hidden = true
        if (label === '关闭详情') button.parentElement?.parentElement?.setAttribute('hidden', '')
        if (button.textContent.trim() === '去聊天里说') {
          const textLabel = Array.from(button.querySelectorAll<HTMLElement>('span'))
            .find(element => element.children.length === 0 && element.textContent.trim() === '去聊天里说')
          const textNode = Array.from(button.childNodes)
            .find(node => node.nodeType === Node.TEXT_NODE && node.textContent?.trim() === '去聊天里说')
          if (textLabel) textLabel.textContent = '继续讨论'
          else if (textNode) textNode.textContent = '继续讨论'
          button.setAttribute('aria-label', '继续讨论计划')
          button.title = '返回对话补充意见，当前计划暂不执行'
        }
        if (button.textContent.trim() === '拒绝') {
          button.textContent = '拒绝并修改'
          button.title = '保留计划模式，并把修改意见交给助手'
        }
        if (button.textContent.trim() === '确认执行') {
          button.title = '批准计划，从下一步开始执行'
        }
      }
      for (const region of document.querySelectorAll<HTMLElement>('[role="region"], section[aria-label]')) {
        if (region.getAttribute('aria-label') === 'Approve this plan and leave plan mode?')
          region.setAttribute('aria-label', '审核健康计划')
      }
      for (const element of document.querySelectorAll<HTMLElement>('[aria-label], [title]')) {
        for (const attribute of ['aria-label', 'title'] as const) {
          const value = element.getAttribute(attribute)
          if (value === null) continue
          const cleaned = value.replace(
            /\/(?:Users|home)\/[^\s'"`]+\/(?:data\/workspace\/)?([^\s'"`/]+(?:\.[\p{L}\p{N}_-]+)?)/giu,
            '当前账号工作区/$1',
          )
          if (cleaned !== value) element.setAttribute(attribute, cleaned)
        }
      }
      const textWalker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
      let textNode = textWalker.nextNode()
      while (textNode !== null) {
        const parent = textNode.parentElement
        if (parent !== null && !['SCRIPT', 'STYLE'].includes(parent.tagName)) {
          const value = textNode.textContent ?? ''
          if (/最大轮次(?:限制)?[：:]\s*\d+\s*轮?/u.test(value)) {
            const row = parent.closest<HTMLElement>('li') ?? parent
            row.hidden = true
            textNode = textWalker.nextNode()
            continue
          }
          const cleaned = removeInternalBrand(value)
            .replace(/~\/[^\s'"`]*packages\/gerclaw\/skills\/skills\/[^\s'"`]+\/SKILL\.md/giu, 'GerClaw 内置能力说明')
            .replace(/gerclaw-(?:medical-sf-v2|med-knowledge)/giu, '本地医学资料库')
            .replace(/\bgoal-[a-z0-9-]{16,}\b/giu, '当前健康目标')
            .replace(/\bget_goal\b/gu, '查看目标')
            .replace(/\b(?:update_goal|create_goal)\b/gu, '更新目标')
            .replace(/查看目标\s*·\s*\{[^}]*\}/gu, '已查看目标进度')
            .replace(/更新目标\s*·\s*[a-z_-]+/giu, '已更新目标状态')
            .replace(/更新目标\s*\([^)]*\)/gu, '更新目标')
            .replace(/目标\s*ID[：:]/gu, '当前目标：')
            .replace(/修订版本[：:]\s*\d+/gu, '状态记录已更新')
            .replace(/阶段[：:]\s*active(?:（已激活）)?/giu, '当前状态：进行中')
            .replace(/阶段[：:]\s*complete(?:（已完成）)?/giu, '当前状态：已完成')
            .replace(/激活状态[：:]\s*disarmed(?:（已解除武装）)?/giu, '目标状态：已结束')
            .replace(/:\s*active(?:（已激活）)?/giu, '：进行中')
            .replace(/:\s*complete(?:（已完成）)?/giu, '：已完成')
            .replace(/:\s*disarmed(?:（已解除武装）)?/giu, '：已结束')
            .replace(/\.gerclaw-rag\/[a-f0-9]{16,64}\.md/giu, '本地医学参考资料')
            .replace(
              /\/(?:Users|home)\/[^\s'"`]+\/(?:data\/workspace\/)?([^\s'"`/]+(?:\.[\p{L}\p{N}_-]+)?)/giu,
              '当前账号工作区/$1',
            )
          if (cleaned !== value) textNode.textContent = cleaned
        }
        textNode = textWalker.nextNode()
      }
      for (const metric of document.querySelectorAll<HTMLElement>('span')) {
        if (!metric.textContent.includes('首 token')) continue
        if (metric.children.length === 0) {
          metric.hidden = true
          continue
        }
        const publicTiming = metric.textContent.match(/^([\s\S]*?)\s*·\s*首 token/u)?.[1]?.trim()
        if (publicTiming) metric.textContent = publicTiming
      }
      const medicalNav = document.querySelector<HTMLElement>('[data-gerclaw-medical-nav]')
      let shell = medicalNav?.parentElement
      while (
        shell
        && !shell.querySelector('button[aria-label="搜索会话"]')
      ) shell = shell.parentElement
      if (medicalNav && shell) {
        medicalNav.dataset.gerclawNavActions = ''
        shell.dataset.gerclawSidebarShell = ''
        let wrapper = medicalNav.parentElement
        while (wrapper && wrapper !== shell) {
          wrapper.dataset.gerclawSidebarFoot = ''
          wrapper = wrapper.parentElement
        }
        const settings = shell.querySelector<HTMLElement>('[data-gerclaw-settings-trigger]')
        if (settings) {
          settings.dataset.gerclawSidebarSettings = ''
          wrapper = settings.parentElement
          while (wrapper && wrapper !== shell) {
            wrapper.dataset.gerclawSidebarFoot = ''
            wrapper = wrapper.parentElement
          }
        }
        for (const child of shell.children) {
          if (!(child instanceof HTMLElement)) continue
          if (child.querySelector('button[aria-label="搜索会话"]'))
            child.dataset.gerclawConversationHistory = ''
          if (child.matches('button[aria-label="新建会话"]'))
            child.dataset.gerclawNewConversation = ''
        }
      }
      if (sessionStorage.getItem('gerclaw.newConversationOnBoot') === '1') {
        const newConversation = Array.from(
          document.querySelectorAll<HTMLButtonElement>('button[aria-label="新建会话"]'),
        ).find(button => button.textContent.trim() === '新会话')
        if (newConversation && !newConversation.disabled) {
          sessionStorage.removeItem('gerclaw.newConversationOnBoot')
          newConversation.click()
        }
      }
    }
    copy()
    let copyTimer: number | undefined
    const scheduleCopy = (): void => {
      if (copyTimer !== undefined) return
      copyTimer = window.setTimeout(() => {
        copyTimer = undefined
        copy()
      }, 24)
    }
    // Native conversation rendering can append many text nodes per second
    // while a response streams. Coalesce those mutations so product copy and
    // sidebar markers never turn token rendering into repeated whole-page
    // synchronous scans.
    const observer = new MutationObserver(scheduleCopy)
    observer.observe(document.documentElement, { childList: true, subtree: true })
    let initialDesktopSidebarExpanded = false
    const expandDesktopSidebar = (): void => {
      if (initialDesktopSidebarExpanded || window.innerWidth < 1200) return
      if (document.querySelector('[data-sidebar-collapsed]') === null) return
      initialDesktopSidebarExpanded = true
      ctx.layout.toggleSidebar()
    }
    expandDesktopSidebar()
    const layoutObserver = new MutationObserver(expandDesktopSidebar)
    layoutObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-sidebar-collapsed'],
      childList: true,
      subtree: true,
    })
    ctx.effect(() => () => {
      observer.disconnect()
      layoutObserver.disconnect()
      if (copyTimer !== undefined) window.clearTimeout(copyTimer)
      document.title = prior
    }, 'gerclaw client: product copy')
  }
  ctx.effect(() => ctx.theme.overrideTokens('@gerclaw/client-ui', {
    '--dsw-alias-bg-base': { light: '#f8fbfd', dark: '#152431' },
    '--dsw-alias-bg-layer-1': { light: '#eef7ff', dark: '#1b3041' },
    '--dsw-alias-bg-layer-2': { light: '#e5f1f9', dark: '#22394b' },
    '--dsw-alias-bg-overlay': { light: '#ffffff', dark: '#1a2c3a' },
    '--dsw-alias-border-l1': { light: '#d8e7f1', dark: '#395164' },
    '--dsw-alias-border-l2': { light: '#c8ddea', dark: '#486275' },
    '--dsw-alias-brand-primary': { light: '#3b82c4', dark: '#78b9e8' },
    '--dsw-alias-label-primary': { light: '#173f63', dark: '#e5f3fc' },
    '--dsw-alias-label-secondary': { light: '#526f84', dark: '#b8cfdf' },
    '--dsw-specific-sidebar-fill': { light: '#edf6fc', dark: '#192b39' },
  }), 'gerclaw client: theme tokens')

  ctx.slots.inject('sidebar.brand.mark', () =>
    ctx.slots.inject('sidebar.brand.name', () =>
      ctx.slots.inject('conversation.hero.brand.mark', function* () {
        yield ctx.slots.register({ name: 'sidebar.brand.mark' }, GerclawBrandMark)
        yield ctx.slots.register({ name: 'sidebar.brand.name' }, GerclawBrandName)
        yield ctx.slots.register({ name: 'conversation.hero.brand.mark' }, GerclawBrandMark)
      })))

  ctx.slots.inject('sidebar.footer.action', () => ctx.slots.register({
    name: 'sidebar.footer.action',
    id: 'gerclaw-medical-navigation',
    order: -100,
    label: '健康功能',
    inject: (): MedicalNavigationInjected => ({
      getSessionId: () => ctx.sessions.list.getSnapshot().current,
      ensureSessionId: async () => {
        const current = ctx.sessions.list.getSnapshot().current
        if (current !== undefined) return current
        const workspaces = ctx.workspaces.list.getSnapshot()
        const workspaceId = workspaces.recentWorkspaceId ?? workspaces.items[0]?.workspaceId
        if (workspaceId === undefined) throw new Error('健康工作区尚未就绪，请稍后重试')
        const sessionId = await ctx.workspaces.connectWorkspace(workspaceId)
        ctx.sessions.open(sessionId)
        return sessionId
      },
      startPrescription: async (sessionId) => {
        const scoped = ctx.sessions.scope(sessionId as never)
        const conversation = scoped?.get('conversation') as
          | { send(text: string): Promise<void> }
          | undefined
        if (conversation === undefined)
          throw new Error('健康对话尚未就绪，请稍后重试')
        await conversation.send('我想开始一份新的五大处方。请在当前对话中收集资料；如果信息不足，每次只问我一个问题。')
      },
      medicalRemote,
    }),
  }, MedicalNavigation))

  ctx.slots.inject('sidebar.settings', () => ctx.slots.register({
    name: 'sidebar.settings',
  }, FriendlySettings))

  ctx.slots.inject('conversation.chat.node', () => ctx.slots.register({
    name: 'conversation.chat.node',
    key: 'gerclaw-task',
    inject: sessionId => ({ sessionId, medicalRemote }),
  }, MedicalTaskCard))

  ctx.slots.inject('conversation.hero.agentPreset', () => ctx.slots.register({
    name: 'conversation.hero.agentPreset',
  }, QuickPrompts))

  ctx.slots.inject('conversation.input.left', () => ctx.slots.register({
    name: 'conversation.input.left',
    id: 'gerclaw-document-upload',
    order: -50,
    inject: sessionId => ({ sessionId }),
  }, ConversationDocumentUpload))

  const ArtifactsTabWithEvents = (props: Parameters<typeof ArtifactsTab>[0]) => createElement(ArtifactsTab, {
    ...props,
    subscribe: (sessionId: string, listener: () => void) => ctx.on(
      'gerclaw/artifacts-created',
      (createdFor) => { if (createdFor === sessionId) listener() },
    ),
  })
  ctx.effect(() => ctx.betterSidebar.registerTab({
    id: 'gerclaw-artifacts',
    title: '产物',
    order: -100,
    single: true,
    component: ArtifactsTabWithEvents,
  }), 'gerclaw client: artifacts tab')

  const openedArtifactSessions = new Set<string>()
  const ensureArtifactTab = (): void => {
    const snapshot = ctx.betterSidebar.getSnapshot()
    const sessionId = snapshot.sessionId
    if (sessionId === undefined || openedArtifactSessions.has(sessionId)) return
    openedArtifactSessions.add(sessionId)
    ctx.betterSidebar.openTab({ type: 'gerclaw-artifacts' }, { sessionId })
  }
  ctx.effect(() => {
    const off = ctx.betterSidebar.subscribeState(ensureArtifactTab)
    ensureArtifactTab()
    return off
  }, 'gerclaw client: open artifacts tab per session')
  ctx.on('gerclaw/artifacts-created', (sessionId) => {
    ctx.betterSidebar.openTab({ type: 'gerclaw-artifacts' }, { sessionId })
  })

  const disabledTabs = Object.fromEntries([
    'editor', 'git', 'subagent', 'sidechat', 'terminal', 'browser', 'diff',
  ].map(id => [id, false]))
  const controller = new AbortController()
  ctx.effect(() => {
    void fetch('/sidebar/api/settings.update', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        patch: {
          openByDefault: true,
          defaultWidthPercent: 25,
          autoOpenSubagent: false,
          autoOpenJobs: false,
          agentTerminalTools: false,
          bottomPanelAutoTerminal: false,
          interceptOpenPath: false,
          browserInterceptLinks: false,
          tabsEnabled: { ...disabledTabs, 'gerclaw-artifacts': true },
        },
      }),
      signal: controller.signal,
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) console.error('[gerclaw] 无法应用产物栏偏好', error)
    })
    return () => { controller.abort() }
  }, 'gerclaw client: artifacts-only sidebar preferences')
}
