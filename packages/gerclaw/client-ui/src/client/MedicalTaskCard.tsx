import type { InjectFace, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import { TaskResult, type MedicalRemoteActions } from './MedicalFeature.tsx'

export interface MedicalTaskCardInjected {
  sessionId: string
  medicalRemote: MedicalRemoteActions
}
export type MedicalTaskCardProps = PropsRuntime<'conversation.chat.node', 'gerclaw-task'>
  & InjectFace<MedicalTaskCardInjected>

/** Native conversation renderer for a restored GerClaw business task. */
export function MedicalTaskCard({ node, sessionId, medicalRemote }: MedicalTaskCardProps) {
  return (
    <article
      data-gerclaw-conversation-task
      data-gerclaw-task-id={node.data.taskId}
      aria-label="医疗任务结果"
    >
      <TaskResult response={{ task: node.data, result: node.data.result }} sessionId={sessionId} remote={medicalRemote} />
    </article>
  )
}
