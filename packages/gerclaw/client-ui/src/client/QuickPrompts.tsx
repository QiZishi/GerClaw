import { useState } from 'react'

const prompts = [
  '帮我梳理今天最需要关注的健康问题',
  '根据我的情况给出一份健康管理建议',
  '帮我检查当前用药需要注意什么',
] as const

export function QuickPrompts({ send }: { send: (prompt: string) => Promise<void> }) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const select = async (prompt: string): Promise<void> => {
    setPending(true)
    setError('')
    try {
      await send(prompt)
    } catch {
      setError('暂时无法发送，请稍后重试。')
    } finally {
      setPending(false)
    }
  }
  return (
    <div>
      <p data-gerclaw-quick-prompts-title>安心管理每一天</p>
      <div data-gerclaw-quick-prompts aria-label="快捷提问">
        {prompts.map(prompt => (
          <button
            key={prompt}
            type="button"
            title={prompt}
            disabled={pending}
            onClick={() => { void select(prompt) }}
          >
            {prompt}
          </button>
        ))}
      </div>
      {error && <p role="status">{error}</p>}
    </div>
  )
}
