import { useState } from 'react'
import type { InjectFace, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import { Modal } from './Modal.tsx'

const healthActions = [
  ['随访问卷', '/followup 请给我一个简短的健康随访问卷，每次只问一个问题。'],
  ['风险评估', '/risk-assessment 请根据当前对话做一次简短风险评估。'],
  ['健康教育', '/health-education 请根据当前对话给出易懂的健康教育建议。'],
  ['用药提醒', '/medication-reminder 请根据当前对话生成清晰的用药提醒。'],
] as const

interface HealthCapabilitiesInjected {
  submit: (text: string) => Promise<void>
}

type HealthCapabilitiesProps = PropsRuntime<'conversation.input.left'>
  & InjectFace<HealthCapabilitiesInjected>

export function HealthCapabilities({ submit }: HealthCapabilitiesProps) {
  const [open, setOpen] = useState(false)
  const [objective, setObjective] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const run = async (text: string): Promise<void> => {
    setPending(true)
    setError('')
    try {
      await submit(text)
      setOpen(false)
    } catch {
      setError('暂时无法开始，请保留当前内容并稍后重试。')
    } finally {
      setPending(false)
    }
  }
  const runObjective = (kind: 'plan' | 'goal'): void => {
    const value = objective.trim()
    if (!value) {
      setError('请先填写您想完成的健康事项。')
      return
    }
    void run(`/${kind} ${value}`)
  }
  return (
    <>
      <button
        type="button"
        data-gerclaw-capabilities-trigger
        aria-label="计划与健康能力"
        title="计划与健康能力"
        onClick={() => { setOpen(true); setError('') }}
      >
        计划与能力
      </button>
      {open && (
        <Modal title="计划与健康能力" onClose={() => { if (!pending) setOpen(false) }}>
          <div data-gerclaw-feature-form>
            <label>
              我想完成什么
              <textarea
                value={objective}
                disabled={pending}
                placeholder="例如：未来三天早晚记录血压"
                onChange={(event) => { setObjective(event.currentTarget.value) }}
              />
            </label>
            <div data-gerclaw-form-actions>
              <button type="button" disabled={pending} onClick={() => { runObjective('plan') }}>制定计划</button>
              <button type="button" disabled={pending} onClick={() => { runObjective('goal') }}>建立目标</button>
            </div>
            <div data-gerclaw-feature-grid>
              {healthActions.map(([label, command]) => (
                <button key={label} type="button" disabled={pending} onClick={() => { void run(command) }}>
                  <strong>{label}</strong>
                </button>
              ))}
            </div>
            {error && <p role="alert">{error}</p>}
          </div>
        </Modal>
      )}
    </>
  )
}
