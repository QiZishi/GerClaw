/** GerClaw adapter that keeps native Plan review reachable with imperfect providers. */
import type { Context } from '@deepseek-ai/cordis'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import type { SessionEvent } from '@deepseek-ai/dsh-session'
import type {} from '@deepseek-ai/dsh-plan-mode'

const PLUGIN = 'gerclaw'
const EXIT_TOOL = 'exit_plan_mode'

function inTurn(event: SessionEvent, turn: number): boolean {
  return 'turn' in event.data && event.data.turn === turn
}

function assistantText(events: readonly SessionEvent[], turn: number): string {
  const event = events.findLast(candidate => candidate.type === 'assistant/message'
    && candidate.data.turn === turn)
  if (event?.type !== 'assistant/message') return ''
  return event.data.message.content
    .filter(block => block.type === 'text')
    .map(block => block.text)
    .join('\n')
}

/** Whether one native continuation is required before an active Plan turn may stop. */
export function needsPlanReviewContinuation(
  events: readonly SessionEvent[],
  turn: number,
  active: boolean,
): boolean {
  if (!active) return false
  const current = events.filter(event => inTurn(event, turn))
  if (current.some(event => event.type === 'tool/call' && event.data.name === EXIT_TOOL)) return false
  if (current.some(event => event.type === 'user/message'
    && event.data.source.kind === 'plugin'
    && event.data.source.plugin === PLUGIN)) return false
  return /^#{1,6}\s+\S/mu.test(assistantText(events, turn))
}

export const name = 'gerclaw-plan-compliance'
export const inject = ['planMode']

export function apply(ctx: Context): void {
  ctx.on('agent/turn-stopping', ({ agent, turn, signal }) => {
    if (signal.aborted) return
    const plan = ctx.planMode.get(agent)
    const eligible = plan.active && plan.pending !== false
    if (!needsPlanReviewContinuation(agent.session.events, turn, eligible)) return
    agent.steer(createUserMessage({
      content: [{
        type: 'text',
        text: '计划模式一致性检查：上一响应已经形成计划正文，但没有提交审核。不要继续检索，也不要输出普通文本；立即把刚才形成的完整计划作为以 # 标题开头的 Markdown 参数调用 exit_plan_mode。本响应只能包含这一项工具调用。',
      }],
      source: {
        kind: 'plugin',
        plugin: PLUGIN,
        form: 'notice',
        summary: '计划已生成，正在提交审核',
      },
    }))
  })
}
