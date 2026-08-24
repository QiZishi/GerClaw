import type {
  ChatConversationViewNode,
  ConversationNodeDefinition,
} from '@deepseek-ai/dsh-client-runtime/client'
import type { Task } from './MedicalFeature.tsx'

declare module '@deepseek-ai/dsh-client-ui-conversation/client' {
  interface ChatNodeDataMap {
    /** A durable GerClaw medical task restored from the native session log. */
    'gerclaw-task': Task
  }
}

interface GerclawTaskEvent {
  readonly type: 'gerclaw/task'
  readonly seq: number
  readonly data: { readonly version: 1; readonly task: Task }
}

function taskEvent(event: unknown): GerclawTaskEvent | undefined {
  if (event === null || typeof event !== 'object') return undefined
  const candidate = event as { type?: unknown; seq?: unknown; data?: unknown }
  if (candidate.type !== 'gerclaw/task'
    || typeof candidate.seq !== 'number'
    || candidate.data === null
    || typeof candidate.data !== 'object') return undefined
  const data = candidate.data as { version?: unknown; task?: unknown }
  if (data.version !== 1 || data.task === null || typeof data.task !== 'object') return undefined
  return candidate as GerclawTaskEvent
}

/** Fold each completed medical task event into one persistent chat card. */
export const medicalTaskDefinition: ConversationNodeDefinition<Task> = {
  kind: 'gerclaw-task',
  target: 'chat',
  match: (event) => {
    const matched = taskEvent(event)
    if (matched === undefined) return null
    return {
      id: String(matched.data.task.taskId ?? matched.seq),
      role: matched.data.task.status === 'running' ? 'start' : 'update',
    }
  },
  start: (_context, match) => {
    const matched = taskEvent(match.event)
    if (matched === undefined) throw new Error('gerclaw-task start requires gerclaw/task')
    return matched.data.task
  },
  update: (context, match) => taskEvent(match.event)?.data.task ?? context.state,
  buildViewNode: (context): ChatConversationViewNode | null => {
    if (context.start === undefined || context.state === undefined) return null
    return {
      key: context.key,
      kind: 'gerclaw-task',
      id: context.id,
      target: 'chat',
      anchorSeq: context.start.event.seq,
      location: context.start.location,
      visibility: 'visible',
      data: context.state,
    }
  },
}
