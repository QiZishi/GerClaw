import type { ChatNodeViewProps } from '@deepseek-ai/dsh-client-ui-conversation/client'

export function RecoverableTurnError(_: ChatNodeViewProps<'turn-error'>) {
  return (
    <div data-gerclaw-recoverable-error role="status">
      <strong>暂时无法连接健康助手</strong>
      <span>刚才的内容仍在当前对话中，请稍后重试。</span>
    </div>
  )
}
