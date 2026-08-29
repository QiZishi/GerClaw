import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'
import { createElement } from 'react'
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type {} from '@deepseek-ai/dsh-client-ui-theme/client'
import type { SessionId } from '@deepseek-ai/dsh-session'
import type {} from 'dsh-better-sidebar/client'
import gerclawAppRemote from '@gerclaw/app/remote'
import type { ArtifactDescriptor, GerclawJsonValue, MedicalTaskKind } from '@gerclaw/app/types'
import { ArtifactsTab } from './ArtifactsTab.tsx'
import { GerclawBrandMark, GerclawBrandName } from './Brand.tsx'
import {
  ConversationDocumentUpload,
  type ConversationDocumentUploadInjected,
} from './ConversationDocumentUpload.tsx'
import { FriendlySettings } from './FriendlySettings.tsx'
import { HealthCapabilities } from './HealthCapabilities.tsx'
import { MedicalNavigation, type MedicalNavigationInjected } from './MedicalNavigation.tsx'
import type { MedicalRemoteActions } from './MedicalFeature.tsx'
import { MedicalTaskCard } from './MedicalTaskCard.tsx'
import { medicalTaskDefinition } from './medical-task-definition.ts'
import { QuickPrompts } from './QuickPrompts.tsx'
import { RecoverableTurnError } from './RecoverableTurnError.tsx'
import { installProductStyles } from './styles.ts'

export const inject = ['slots', 'theme', 'betterSidebar', 'sessions', 'workspaces', 'conversation', 'conversationEvents', 'remote', 'locale']

declare module '@deepseek-ai/cordis' {
  interface Events {
    /** A GerClaw export completed in this browser client. */
    'gerclaw/artifacts-created'(sessionId: SessionId): void
  }
}

export async function apply(ctx: ClientContext): Promise<void> {
  ctx.locale.setLocale('zh')
  const disposeRemote = await ctx.remote.$mount(gerclawAppRemote)
  ctx.effect(() => async () => { await disposeRemote() }, 'gerclaw client: medical remote')
  const ensureSessionId = async (): Promise<SessionId> => {
    const current = ctx.sessions.list.getSnapshot().current
    if (current !== undefined) return current
    const workspaces = ctx.workspaces.list.getSnapshot()
    const workspaceId = workspaces.recentWorkspaceId ?? workspaces.items[0]?.workspaceId
    if (workspaceId === undefined) throw new Error('健康对话尚未就绪，请稍后重试')
    const sessionId = await ctx.workspaces.connectWorkspace(workspaceId)
    ctx.sessions.open(sessionId)
    return sessionId
  }
  const sendConversationMessage = async (text: string, sessionId?: SessionId): Promise<void> => {
    const selected = sessionId ?? await ensureSessionId()
    const conversation = ctx.sessions.scope(selected as never)?.get('conversation') as
      | { send(text: string): Promise<void> }
      | undefined
    if (conversation === undefined) throw new Error('健康对话尚未就绪，请稍后重试')
    await conversation.send(text)
  }
  const submitComposerText = async (text: string): Promise<void> => {
    const sessionId = await ensureSessionId()
    const actx = ctx.sessions.scope(sessionId)
    if (actx === undefined) throw new Error('健康对话尚未就绪，请稍后重试')
    const input = ctx.conversation.input.for(actx)
    input.setDraft(text)
    input.submit()
  }
  ctx.conversationEvents.register(medicalTaskDefinition)
  installProductStyles(ctx)
  if (typeof document !== 'undefined') {
    const priorTitle = document.title
    document.title = 'GerClaw｜老年慢病智慧诊疗助手'
    ctx.effect(() => () => { document.title = priorTitle }, 'gerclaw client: product title')
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
        yield ctx.slots.register({ name: 'sidebar.brand.mark', priority: -100 }, GerclawBrandMark)
        yield ctx.slots.register({ name: 'sidebar.brand.name', priority: -100 }, GerclawBrandName)
        yield ctx.slots.register({ name: 'conversation.hero.brand.mark', priority: -100 }, GerclawBrandMark)
      })))

  ctx.inject(['remote.gerclawApp'], (ctx) => {
    const medicalRemote: MedicalRemoteActions = {
      submit: async (
        kind: MedicalTaskKind,
        sessionId: string,
        input: GerclawJsonValue,
        requestId: string,
        signal: AbortSignal,
      ) => {
        const result = await ctx.remote.gerclawApp.submit(
          sessionId as SessionId,
          { requestId, kind, input },
          signal,
        )
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
    ctx.slots.inject('sidebar.footer.action', () => ctx.slots.register({
      name: 'sidebar.footer.action',
      id: 'gerclaw-medical-navigation',
      order: -100,
      label: '健康功能',
      inject: (): MedicalNavigationInjected => ({
        getSessionId: () => ctx.sessions.list.getSnapshot().current,
        ensureSessionId,
        startPrescription: async (sessionId) => {
          await sendConversationMessage(
            '我想开始一份新的五大处方。请在当前对话中收集资料；如果信息不足，每次只问我一个问题。',
            sessionId as SessionId,
          )
        },
        medicalRemote,
      }),
    }, MedicalNavigation))

    ctx.slots.inject('conversation.chat.node', () => ctx.slots.register({
      name: 'conversation.chat.node',
      key: 'gerclaw-task',
      inject: sessionId => ({ sessionId, medicalRemote }),
    }, MedicalTaskCard))
  })

  ctx.slots.inject('sidebar.settings', () => ctx.slots.register({
    name: 'sidebar.settings',
  }, FriendlySettings))

  ctx.slots.inject('conversation.chat.node', () => ctx.slots.register({
    name: 'conversation.chat.node',
    key: 'turn-error',
    priority: -100,
    locale: 'conversation',
  }, RecoverableTurnError))

  ctx.slots.inject('conversation.hero.agentPreset', () => ctx.slots.register({
    name: 'conversation.hero.agentPreset',
    inject: () => ({ send: submitComposerText }),
  }, QuickPrompts))

  ctx.slots.inject('conversation.input.left', function* () {
    yield ctx.slots.register({
      name: 'conversation.input.left',
      id: 'gerclaw-document-upload',
      order: -50,
      inject: sessionId => ({
        sessionId,
        getVoiceFiles: () => ctx.get('gerclawVoiceFiles') as
          ReturnType<ConversationDocumentUploadInjected['getVoiceFiles']>,
      }),
    }, ConversationDocumentUpload)
    yield ctx.slots.register({
      name: 'conversation.input.left',
      id: 'gerclaw-health-capabilities',
      order: -40,
      inject: () => ({ submit: submitComposerText }),
    }, HealthCapabilities)
  })

  const getCurrentSessionId = (): string | undefined => ctx.sessions.list.getSnapshot().current
  const ArtifactsTabWithEvents = (props: Parameters<typeof ArtifactsTab>[0]) => createElement(ArtifactsTab, {
    ...props,
    getCurrentSessionId,
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

  ctx.on('gerclaw/artifacts-created', (sessionId) => {
    ctx.betterSidebar.openTab({ type: 'gerclaw-artifacts', path: 'artifacts/' }, { sessionId })
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
          openByDefault: false,
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
